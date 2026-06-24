"""对话编排：LLM + RAG + 上下文管理。

多级降级链路：Dify RAG → LocalRAG + DeepSeek → 通义千问
Token 节省策略：历史压缩 + 高频缓存 + 自适应 max_tokens
"""

import asyncio
import logging
from collections.abc import AsyncGenerator

from cachetools import TTLCache
from openai import AsyncOpenAI

from backend.config import settings
from backend.http_client import get_http_client

logger = logging.getLogger(__name__)

_FALLBACK_THRESHOLD: int = 3
_MAX_SESSION_FAILURES: int = 1000
_PROBE_INTERVAL: int = 5  # 降级后每 N 次请求探测 1 次主链路

# ── Token 节省常量 ────────────────────────────────────────
# 历史压缩：前 N 轮原始历史保留，超出后压缩为摘要
_COMPRESS_AFTER_ROUNDS: int = 6  # 6 轮后触发压缩
_SUMMARY_MAX_TOKENS: int = 300  # 摘要最多占用 Token
_RAW_KEEP_ROUNDS: int = 4  # 压缩后保留最近 4 轮原始消息
# 高频问答缓存（TTLCache，maxsize=1024, ttl=1800s，自动淘汰）
# 自适应 max_tokens
_SHORT_QUERY_LENGTH: int = 10  # ≤10 字视为短查询
_SHORT_MAX_TOKENS: int = 256  # 短查询回答上限
_LONG_MAX_TOKENS: int = 1024  # 长查询回答上限


class ChatBot:
    """对话引擎，负责编排 LLM 与 RAG 检索。

    调用链路（自优先至高）：
    1. Dify RAG（通过 DifyClient）
    2. LocalRAG + DeepSeek API（本地检索增强 + OpenAI 兼容接口）
    3. 通义千问 API（连续 3 次 5xx 时）

    Token 节省机制：
    - 多轮对话超过 6 轮后，自动压缩旧历史为摘要
    - 高频问题（精确命中）走内存缓存，不调 API
    - 短查询（≤10 字）使用更小的 max_tokens
    """

    def __init__(self) -> None:
        self.primary_provider = settings.llm_provider
        self.model = settings.deepseek_model
        self.primary_base_url = settings.deepseek_base_url
        self.primary_api_key = settings.deepseek_api_key
        # 降级配置（从 settings 读取）
        self.fallback_base_url = settings.fallback_llm_base_url
        self.fallback_model = settings.fallback_llm_model
        self.fallback_api_key = settings.fallback_llm_api_key
        self._using_fallback = False
        # per-session 失败计数（避免多用户并发互相干扰）
        self._session_failures: dict[str, int] = {}
        # per-session 对话历史（session_id → messages list）
        self._session_history: dict[str, list[dict]] = {}
        self._max_history: int = 10  # 每个会话保留最近 10 轮
        # ── Token 节省基础设施 ──
        self._cache: TTLCache[str, str] = TTLCache(maxsize=1024, ttl=1800)  # LRU + TTL 问答缓存（30分钟）
        # 压缩摘要存储 {session_id: "摘要文本"}
        self._session_summary: dict[str, str] = {}
        # Token 使用统计 {session_id: total_tokens}
        self._token_usage: dict[str, int] = {}
        self._max_session_tokens: int = 8192  # 单会话 Token 预算上限

    # ═══════════════════════════════════════════════════════════════
    # SECTION: chat() — Non-streaming single-response dialogue
    # TODO: Split into chat_router (input validation + session mgmt)
    #       and chat_engine (LLM call + fallback logic) for testability.
    # ═══════════════════════════════════════════════════════════════

    async def chat(self, query: str, context: str | None = None, session_id: str = "default") -> str | None:
        """生成回答，自动降级，支持多轮对话。

        链路：Dify RAG → LocalRAG + DeepSeek → 通义千问
        Token 节省链：高频缓存查询 → 历史自动压缩 → 自适应 max_tokens

        Args:
            query: 用户输入文本
            context: 可选的 RAG 检索上下文（未接入 Dify 时使用）
            session_id: 会话 ID，用于多轮对话历史

        Returns:
            回答文本或 None
        """
        # ── Token 节省：高频缓存查询 ───────────────────────
        cached = self._check_cache(query)
        if cached:
            logger.info("[ChatBot] 缓存命中: %s", query[:50])
            return cached

        # ── Token 节省：历史自动压缩 ────────────────────────
        self._auto_compress(session_id)

        # ── Per-session 计数器惰性清理 ────────────────────────
        if len(self._session_failures) > 1000:
            active = set(self._session_history.keys())
            stale = [k for k in self._session_failures if k not in active]
            for k in stale:
                self._session_failures.pop(k, None)
            if len(self._session_failures) > 1000:
                keep = sorted(self._session_failures.keys())[-500:]
                self._session_failures = {k: self._session_failures[k] for k in keep}
            logger.info("[ChatBot] session_failures 惰性清理完成，当前 %d 条", len(self._session_failures))

        # ── Token 节省：超预算熔断 ──────────────────────────
        if self._token_usage.get(session_id, 0) > self._max_session_tokens:
            logger.warning("[ChatBot] 会话 %s Token 超预算，清空历史", session_id[:8])
            self.clear_history(session_id)
            self._token_usage[session_id] = 0

        # 阶段 1：优先尝试 Dify RAG（仅 API Key 已配置时）
        if self._dify_configured():
            reply = await self._dify_or_fallback(query, session_id)
            if reply:
                self._add_to_cache(query, reply)
                return reply
            logger.info("[ChatBot] Dify 不可用，降级至直连 DeepSeek")

        # ── 本地 RAG 检索（Dify 降级后、DeepSeek 调用前）──
        rag_context = None
        try:
            from backend.services.local_rag import local_rag as _local_rag

            rag_context = await asyncio.to_thread(_local_rag.search, query)
            if rag_context:
                logger.info("[ChatBot] 本地 RAG 检索到上下文，增强 DeepSeek 回答")
        except Exception:
            logger.debug("[ChatBot] 本地 RAG 不可用（未安装依赖或模型加载失败）")

        # RAG 上下文叠加到原始 context 上（而非替换），保留情绪标签等格式指令
        if rag_context and context:
            effective_context = f"{rag_context}\n\n{context}"
        else:
            effective_context = rag_context or context

        # 阶段 2：原有 DeepSeek → 通义千问逻辑（per-session 降级判断 + 自动恢复探测）
        session_fails = self._session_failures.get(session_id, 0)
        if session_fails >= _FALLBACK_THRESHOLD:
            # 自动恢复探测：每 _PROBE_INTERVAL 次请求尝试 1 次主链路
            if session_fails % _PROBE_INTERVAL == 0:
                logger.info("[ChatBot] 会话 %s 降级探测 (连续失败=%d): 尝试主链路", session_id[:8], session_fails)
            else:
                logger.warning("[ChatBot] 会话 %s 已达降级阈值 (%d 次)，切换到通义千问", session_id[:8], session_fails)
                self._session_failures[session_id] = min(session_fails + 1, _MAX_SESSION_FAILURES)
                return await self._chat_fallback(query, effective_context, session_id)

        # ── Token 节省：自适应 max_tokens ──────────────────
        adaptive_max_tokens = _SHORT_MAX_TOKENS if len(query) <= _SHORT_QUERY_LENGTH else _LONG_MAX_TOKENS

        try:
            client = self._create_client(self.primary_api_key, self.primary_base_url)
            messages = self._build_messages(query, effective_context, session_id)

            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=adaptive_max_tokens,
                timeout=30,
            )
            reply = response.choices[0].message.content
            token_count = response.usage.total_tokens if response.usage else 0
            if reply:
                self._session_failures[session_id] = 0
                self._using_fallback = False
                self._add_history(session_id, query, reply)
                self._add_to_cache(query, reply)
                # 累计 Token 消耗
                self._token_usage[session_id] = self._token_usage.get(session_id, 0) + token_count
                logger.info(
                    "[ChatBot] DeepSeek 回答成功 (tokens=%d, session累计=%d)",
                    token_count,
                    self._token_usage[session_id],
                )
                return reply
            logger.warning("[ChatBot] DeepSeek 返回空回答")
            return None
        except Exception as e:
            current = self._session_failures.get(session_id, 0)
            self._session_failures[session_id] = min(current + 1, _MAX_SESSION_FAILURES)
            logger.error(
                "[ChatBot] DeepSeek 调用失败 (会话 %s 连续 %d 次): %s",
                session_id[:8],
                self._session_failures[session_id],
                e,
                exc_info=True,
            )

            if self._session_failures[session_id] >= _FALLBACK_THRESHOLD:
                logger.warning("[ChatBot] 会话 %s 切换至降级方案：通义千问", session_id[:8])
                return await self._chat_fallback(query, effective_context, session_id)
            return None

    # ── Token 节省：高频缓存 ────────────────────────────

    def _check_cache(self, query: str) -> str | None:
        """检查高频问答缓存（精确匹配）。

        Args:
            query: 用户输入

        Returns:
            缓存的回答或 None
        """
        key = query.strip().lower()
        return self._cache.get(key)

    def _add_to_cache(self, query: str, reply: str) -> None:
        """写入高频问答缓存（TTLCache 自动处理淘汰和 TTL）。

        Args:
            query: 用户输入
            reply: AI 回答
        """
        key = query.strip().lower()
        self._cache[key] = reply

    # ── Token 节省：历史压缩 ────────────────────────────

    def _auto_compress(self, session_id: str) -> None:
        """当历史超过阈值时压缩旧轮次为摘要，腾出上下文窗口。

        保留最近 _RAW_KEEP_ROUNDS 轮原始消息，
        更早的历史压缩为一段 system-level 摘要。

        Args:
            session_id: 会话 ID
        """
        history = self._session_history.get(session_id, [])
        raw_rounds = len(history) // 2  # 每轮 user + assistant
        if raw_rounds <= _COMPRESS_AFTER_ROUNDS:
            return

        keep_msgs = _RAW_KEEP_ROUNDS * 2
        old_msgs = history[:-keep_msgs]
        self._session_history[session_id] = history[-keep_msgs:]

        # 将旧消息压缩为 1-2 句摘要
        summary_parts: list[str] = []
        for msg in old_msgs:
            role = msg["role"]
            content = msg["content"]
            if len(content) > 80:
                content = content[:80] + "…"
            summary_parts.append(f"[{role}] {content}")
        summary = " | ".join(summary_parts)
        if len(summary) > _SUMMARY_MAX_TOKENS:
            summary = summary[:_SUMMARY_MAX_TOKENS] + "…"

        self._session_summary[session_id] = summary
        logger.info(
            "[ChatBot] 会话 %s 历史压缩 (%d→%d轮)，摘要 %d 字",
            session_id[:8],
            raw_rounds,
            _RAW_KEEP_ROUNDS,
            len(summary),
        )

    # ── Dify 双模 ────────────────────────────────────────

    @staticmethod
    def _dify_configured() -> bool:
        """检查 Dify 是否已配置。

        Returns:
            已配置返回 True
        """
        key = settings.dify_api_key
        return bool(key) and key not in ("your-key-here", "")

    async def _dify_or_fallback(self, query: str, session_id: str = "default") -> str | None:
        """优先调 Dify，不可用时返回 None 交给上层降级。

        这是"双模"入口：Dify 在线就用 Dify 回答，
        Dify 不通则返回 None，chat() 自动走 DeepSeek。

        Args:
            query: 用户输入
            session_id: 会话 ID

        Returns:
            回答文本或 None
        """
        try:
            from backend.services.dify_client import dify_client as dc

            result = await dc.chat(query=query, user=session_id)
            if result and "answer" in result:
                answer = result["answer"].strip()
                if answer:
                    self._add_history(session_id, query, answer)
                    logger.info("[ChatBot] Dify 回答成功")
                    return answer
            logger.warning("[ChatBot] Dify 返回空回答")
            return None
        except ImportError:
            logger.warning("[ChatBot] dify_client 模块不可用")
            return None
        except Exception as e:
            logger.warning("[ChatBot] Dify 调用异常: %s", e)
            return None

    @staticmethod
    def _create_client(api_key: str, base_url: str) -> AsyncOpenAI:
        """创建 OpenAI 客户端（复用全局 HTTP 连接池）。

        Args:
            api_key: API 密钥
            base_url: API 基础地址

        Returns:
            AsyncOpenAI 客户端实例
        """
        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=get_http_client(),
        )

    async def _chat_fallback(self, query: str, context: str | None = None, session_id: str = "default") -> str | None:
        """降级方案：通义千问 API。

        Args:
            query: 用户输入
            context: 可选的上下文
            session_id: 会话 ID

        Returns:
            回答文本或 None
        """
        if not self.fallback_api_key:
            logger.error("[ChatBot] 通义千问 API Key 未配置，降级不可用")
            return None
        adaptive_max_tokens = _SHORT_MAX_TOKENS if len(query) <= _SHORT_QUERY_LENGTH else _LONG_MAX_TOKENS
        try:
            client = self._create_client(self.fallback_api_key, self.fallback_base_url)
            messages = self._build_messages(query, context, session_id)
            response = await client.chat.completions.create(
                model=self.fallback_model,
                messages=messages,
                temperature=0.7,
                max_tokens=adaptive_max_tokens,
                timeout=30,
            )
            reply = response.choices[0].message.content
            token_count = response.usage.total_tokens if response.usage else 0
            if reply:
                self._using_fallback = True
                self._add_history(session_id, query, reply)
                self._add_to_cache(query, reply)
                self._token_usage[session_id] = self._token_usage.get(session_id, 0) + token_count
                logger.info(
                    "[ChatBot] 通义千问回答成功 (tokens=%d)",
                    token_count,
                )
            return reply
        except Exception as e:
            self._using_fallback = True
            logger.error("[ChatBot] 通义千问也失败: %s", e, exc_info=True)
            return None

    def _build_messages(self, query: str, context: str | None = None, session_id: str = "default") -> list[dict]:
        """构建消息数组（含多轮历史 + 可选摘要）。

        构建策略（按优先级）：
        1. 有压缩摘要 → 将摘要注入 system prompt
        2. 保留最近 _RAW_KEEP_ROUNDS 轮原始对话
        3. 超出预算 → 清空历史

        Args:
            query: 用户输入
            context: 可选的系统上下文
            session_id: 会话 ID

        Returns:
            消息列表（system + history + user）
        """
        messages: list[dict] = []

        # 构建 system prompt（含上下文 + 可选摘要）
        system_parts: list[str] = []
        if context:
            system_parts.append(context)
        if session_id in self._session_summary:
            summary = self._session_summary[session_id]
            system_parts.append(f"以下是之前对话的要点摘要（用于保持上下文连贯性）：{summary}")
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})

        # 追加最近几轮原始对话历史
        history = self._session_history.get(session_id, [])
        messages.extend(history)
        messages.append({"role": "user", "content": query})
        return messages

    def _add_history(self, session_id: str, query: str, reply: str) -> None:
        """记录对话历史。

        Args:
            session_id: 会话 ID
            query: 用户问题
            reply: AI 回答
        """
        if session_id not in self._session_history:
            self._session_history[session_id] = []
        self._session_history[session_id].append({"role": "user", "content": query})
        self._session_history[session_id].append({"role": "assistant", "content": reply})
        # 超过上限时移除最早的历史（FIFO）
        max_msgs = self._max_history * 2  # 每轮 = user + assistant
        if len(self._session_history[session_id]) > max_msgs:
            self._session_history[session_id] = self._session_history[session_id][-max_msgs:]

    def clear_history(self, session_id: str = "default") -> None:
        """清除指定会话的历史记录、摘要和 Token 统计。

        Args:
            session_id: 会话 ID
        """
        self._session_history.pop(session_id, None)
        self._session_summary.pop(session_id, None)
        self._token_usage.pop(session_id, None)
        logger.info("[ChatBot] 已清除会话 %s 的所有数据", session_id)

    def set_fallback_api_key(self, api_key: str) -> None:
        """设置降级 API Key。"""
        self.fallback_api_key = api_key
        logger.info("[ChatBot] 通义千问 API Key 已设置")

    def get_token_stats(self) -> dict:
        """返回全局 Token 消耗统计。

        Returns:
            {"total_tokens": int, "sessions": int, "cache_size": int, "compressed_sessions": int}
        """
        return {
            "total_tokens": sum(self._token_usage.values()),
            "sessions": len(self._token_usage),
            "cache_size": len(self._cache),
            "cache_hit_rate": "N/A",  # 可在后续迭代中精确统计
            "compressed_sessions": len(self._session_summary),
        }

    @property
    def using_fallback(self) -> bool:
        """当前是否使用降级方案。"""
        return self._using_fallback

    # ── 多模态图片问答 ──────────────────────────────────

    @staticmethod
    def _normalize_image_base64(image_base64: str) -> str:
        """归一化 base64 图片字符串，剥离可选的 data: URI 前缀。

        Args:
            image_base64: 原始 base64 字符串，可能带 data:image/...;base64, 前缀

        Returns:
            纯 base64 编码字符串
        """
        if "," in image_base64 and image_base64.startswith("data:"):
            return image_base64.split(",", 1)[1]
        return image_base64

    async def chat_with_image(self, query: str, image_base64: str, session_id: str = "default") -> str | None:
        """多模态图片问答，调用通义千问VL 模型识别图片内容。

        场景：用户上传景区照片并提问（如"这是什么景点？"）。

        Args:
            query: 用户文字问题
            image_base64: 图片的 base64 编码（纯编码，不含 data: URI 前缀）
            session_id: 会话 ID

        Returns:
            AI 回答文本，API Key 为空或调用失败时返回降级提示
        """
        if not settings.multimodal_api_key:
            logger.warning("[ChatBot] 多模态 API Key 未配置，返回降级提示")
            return "暂不支持图片识别，您可以用文字描述图片内容，我会尽力帮您解答。"

        normalized_b64 = self._normalize_image_base64(image_base64)

        try:
            client = self._create_client(settings.multimodal_api_key, settings.fallback_llm_base_url)

            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是无锡灵山胜境的AI导游灵灵。"
                        "用户上传了一张景区照片，请根据图片内容回答问题。"
                        "热情专业口语化，介绍景点/历史/宗教/路线/美食。回答 ≤ 100 字。"
                        "末尾附 [情绪: happy/sad/angry/surprise/neutral]。"
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": query},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{normalized_b64}"},
                        },
                    ],
                },
            ]

            response = await client.chat.completions.create(
                model=settings.multimodal_model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
                timeout=30,
            )

            reply = response.choices[0].message.content
            if reply:
                token_count = response.usage.total_tokens if response.usage else 0
                self._add_history(session_id, f"[图片] {query}", reply)
                # 不写入文本缓存：图片问答结果带视觉上下文，混入纯文本缓存会导致后续纯文本用户得到错误回答
                self._token_usage[session_id] = self._token_usage.get(session_id, 0) + token_count
                logger.info(
                    "[ChatBot] 多模态回答成功 (model=%s, tokens=%d)",
                    settings.multimodal_model,
                    token_count,
                )
                return reply

            logger.warning("[ChatBot] 多模态返回空回答")
            return "抱歉，我无法识别这张图片，请换一个角度拍摄或描述您的问题。"

        except Exception as e:
            logger.error("[ChatBot] 多模态调用失败: %s", e, exc_info=True)
            return "图片识别服务暂时不可用，您可以用文字描述图片内容，我会尽力帮您解答。"

    # ── 流式对话 ────────────────────────────────────────

    # ═══════════════════════════════════════════════════════════════
    # SECTION: chat_stream() — Streaming token-by-token dialogue
    # TODO: Split into stream_router (SSE framing + sentence splitting)
    #       and stream_engine (LLM streaming + fallback).
    # ═══════════════════════════════════════════════════════════════

    async def chat_stream(
        self,
        query: str,
        context: str | None = None,
        session_id: str = "default",
    ) -> AsyncGenerator[str, None]:
        """逐 token 流式对话，自动降级。

        Token 节省链：高频缓存 → 历史自动压缩 → 自适应 max_tokens
        降级链：DeepSeek streaming → 通义千问 streaming

        Args:
            query: 用户输入文本
            context: 可选的 RAG 检索上下文
            session_id: 会话 ID

        Yields:
            文本 token
        """
        # ── 缓存命中 → 直接返回 ─────────────────────────
        cached = self._check_cache(query)
        if cached:
            logger.info("[ChatBot] 流式缓存命中: %s", query[:50])
            yield cached
            return

        # ── 历史压缩 ──────────────────────────────────────
        self._auto_compress(session_id)

        # ── Token 超预算熔断 ──────────────────────────────
        if self._token_usage.get(session_id, 0) > self._max_session_tokens:
            logger.warning("[ChatBot] 会话 %s Token 超预算，清空历史", session_id[:8])
            self.clear_history(session_id)
            self._token_usage[session_id] = 0

        # ── 降级判断 ────────────────────────────────────
        session_fails = self._session_failures.get(session_id, 0)
        if session_fails >= _FALLBACK_THRESHOLD:
            if session_fails % _PROBE_INTERVAL == 0:
                logger.info("[ChatBot] 会话 %s 降级探测: 尝试主链路", session_id[:8])
            else:
                logger.warning("[ChatBot] 会话 %s 降级流式 → 通义千问", session_id[:8])
                self._session_failures[session_id] = min(session_fails + 1, _MAX_SESSION_FAILURES)
                async for token in self._chat_stream_fallback(query, context, session_id):
                    yield token
                return

        adaptive_max_tokens = _SHORT_MAX_TOKENS if len(query) <= _SHORT_QUERY_LENGTH else _LONG_MAX_TOKENS

        # ── 本地 RAG 检索（增强上下文） ──────────────────
        rag_context = None
        try:
            from backend.services.local_rag import local_rag as _local_rag

            rag_context = await asyncio.to_thread(_local_rag.search, query)
            if rag_context:
                logger.info("[ChatBot] 流式本地 RAG 检索到上下文")
        except Exception:
            logger.debug("[ChatBot] 流式本地 RAG 不可用")

        # RAG 上下文叠加到原始 context 上（而非替换），保留情绪标签等格式指令
        if rag_context and context:
            effective_context = f"{rag_context}\n\n{context}"
        else:
            effective_context = rag_context or context

        # ── DeepSeek 流式 ─────────────────────────────────
        full_reply: list[str] = []
        last_usage = None

        try:
            client = self._create_client(self.primary_api_key, self.primary_base_url)
            messages = self._build_messages(query, effective_context, session_id)

            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=adaptive_max_tokens,
                timeout=30,
                stream=True,
            )

            async for chunk in response:
                # 记录 usage（streaming 模式下仅在最后 chunk 有值）
                if chunk.usage:
                    last_usage = chunk.usage

                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_reply.append(token)
                    yield token

            reply_text = "".join(full_reply)
            if reply_text:
                self._session_failures[session_id] = 0
                self._using_fallback = False
                self._add_history(session_id, query, reply_text)
                self._add_to_cache(query, reply_text)
                token_count = last_usage.total_tokens if last_usage else max(len(reply_text) // 2, 1)
                self._token_usage[session_id] = self._token_usage.get(session_id, 0) + token_count
                logger.info(
                    "[ChatBot] DeepSeek 流式成功 (约 %d tokens)",
                    token_count,
                )
            else:
                logger.warning("[ChatBot] DeepSeek 流式返回空回答")

        except Exception as e:
            current = self._session_failures.get(session_id, 0)
            self._session_failures[session_id] = min(current + 1, _MAX_SESSION_FAILURES)
            logger.error(
                "[ChatBot] DeepSeek 流式失败 (会话 %s 连续 %d 次): %s",
                session_id[:8],
                self._session_failures[session_id],
                e,
                exc_info=True,
            )

            # 已有部分 token 时，不再降级（避免重复上下文）
            if full_reply:
                partial = "".join(full_reply)
                if partial.strip():
                    self._add_history(session_id, query, partial)
                    self._add_to_cache(query, partial)
                return

            # 无任何 token 时尝试降级
            if self._session_failures[session_id] >= _FALLBACK_THRESHOLD:
                logger.warning("[ChatBot] 流式切换至降级方案：通义千问")
                async for token in self._chat_stream_fallback(query, effective_context, session_id):
                    full_reply.append(token)
                    yield token
                reply_text = "".join(full_reply)
                if reply_text:
                    self._add_history(session_id, query, reply_text)
                    self._add_to_cache(query, reply_text)

    async def _chat_stream_fallback(
        self,
        query: str,
        context: str | None = None,
        session_id: str = "default",
    ) -> AsyncGenerator[str, None]:
        """降级方案：通义千问流式 API。

        Args:
            query: 用户输入
            context: 可选的上下文
            session_id: 会话 ID

        Yields:
            文本 token
        """
        if not self.fallback_api_key:
            logger.error("[ChatBot] 通义千问 API Key 未配置，流式降级不可用")
            return

        adaptive_max_tokens = _SHORT_MAX_TOKENS if len(query) <= _SHORT_QUERY_LENGTH else _LONG_MAX_TOKENS
        try:
            client = self._create_client(self.fallback_api_key, self.fallback_base_url)
            messages = self._build_messages(query, context, session_id)
            response = await client.chat.completions.create(
                model=self.fallback_model,
                messages=messages,
                temperature=0.7,
                max_tokens=adaptive_max_tokens,
                timeout=30,
                stream=True,
            )

            full_reply: list[str] = []
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    token = chunk.choices[0].delta.content
                    full_reply.append(token)
                    yield token

            reply_text = "".join(full_reply)
            if reply_text:
                self._using_fallback = True
                self._add_history(session_id, query, reply_text)
                self._add_to_cache(query, reply_text)
                logger.info("[ChatBot] 通义千问流式成功")
        except Exception as e:
            logger.error("[ChatBot] 通义千问流式也失败: %s", e, exc_info=True)


chatbot = ChatBot()
