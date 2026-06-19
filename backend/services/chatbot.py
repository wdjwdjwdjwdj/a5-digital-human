"""对话编排：LLM + RAG + 上下文管理。

多级降级链路：Dify RAG → LocalRAG + DeepSeek → 通义千问
Token 节省策略：历史压缩 + 高频缓存 + 自适应 max_tokens
"""

import asyncio
import logging
import ssl
from collections import OrderedDict

import httpx
from openai import AsyncOpenAI

from backend.config import settings

logger = logging.getLogger(__name__)

_FALLBACK_THRESHOLD: int = 3

# ── Token 节省常量 ────────────────────────────────────────
# 历史压缩：前 N 轮原始历史保留，超出后压缩为摘要
_COMPRESS_AFTER_ROUNDS: int = 6  # 6 轮后触发压缩
_SUMMARY_MAX_TOKENS: int = 300  # 摘要最多占用 Token
_RAW_KEEP_ROUNDS: int = 4  # 压缩后保留最近 4 轮原始消息
# 高频问答缓存
_CACHE_MAX_SIZE: int = 20  # LRU 缓存最多 20 条
_CACHE_EXACT_ONLY: bool = True  # 仅缓存精确命中（防语义模糊误匹配）
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
        # 实例级失败计数（避免多用户并发问题）
        self._consecutive_failures: int = 0
        # per-session 对话历史（session_id → messages list）
        self._session_history: dict[str, list[dict]] = {}
        self._max_history: int = 10  # 每个会话保留最近 10 轮
        # ── Token 节省基础设施 ──
        self._cache: OrderedDict[str, str] = OrderedDict()  # LRU 问答缓存
        # 压缩摘要存储 {session_id: "摘要文本"}
        self._session_summary: dict[str, str] = {}
        # Token 使用统计 {session_id: total_tokens}
        self._token_usage: dict[str, int] = {}
        self._max_session_tokens: int = 8192  # 单会话 Token 预算上限

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

        # 用 local_rag 结果覆盖 context（如果检索到内容）
        effective_context = rag_context or context

        # 阶段 2：原有 DeepSeek → 通义千问逻辑
        if self._consecutive_failures >= _FALLBACK_THRESHOLD:
            logger.warning("[ChatBot] 已达降级阈值，切换到通义千问")
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
                self._consecutive_failures = 0
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
            self._consecutive_failures += 1
            logger.error(
                "[ChatBot] DeepSeek 调用失败 (连续 %d 次): %s",
                self._consecutive_failures,
                e,
                exc_info=True,
            )

            if self._consecutive_failures >= _FALLBACK_THRESHOLD:
                logger.warning("[ChatBot] 切换至降级方案：通义千问")
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
        if key in self._cache:
            # LRU 刷新：移到末尾
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _add_to_cache(self, query: str, reply: str) -> None:
        """写入高频问答缓存（LRU 淘汰）。

        Args:
            query: 用户输入
            reply: AI 回答
        """
        key = query.strip().lower()
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = reply
        if len(self._cache) > _CACHE_MAX_SIZE:
            self._cache.popitem(last=False)
            logger.debug("[ChatBot] 缓存淘汰（已达上限 %d）", _CACHE_MAX_SIZE)

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
        """创建 OpenAI 客户端。

        Args:
            api_key: API 密钥
            base_url: API 基础地址

        Returns:
            AsyncOpenAI 客户端实例
        """
        import certifi

        # 使用 certifi 提供的最新 CA 证书包
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        http_client = httpx.AsyncClient(
            verify=ssl_context,
            trust_env=False,
        )
        return AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
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


chatbot = ChatBot()
