"""对话编排：LLM + RAG + 上下文管理。

多级降级链路：Dify RAG → DeepSeek → 通义千问
"""

import logging
import ssl

import httpx
from openai import AsyncOpenAI

from backend.config import settings

logger = logging.getLogger(__name__)

_FALLBACK_THRESHOLD: int = 3


class ChatBot:
    """对话引擎，负责编排 LLM 与 RAG 检索。

    调用链路（自优先至高）：
    1. Dify RAG（通过 DifyClient）
    2. DeepSeek API（OpenAI 兼容接口）
    3. 通义千问 API（连续 3 次 5xx 时）
    """

    def __init__(self) -> None:
        self.primary_provider = settings.llm_provider
        self.model = settings.deepseek_model
        self.primary_base_url = settings.deepseek_base_url
        self.primary_api_key = settings.deepseek_api_key
        # 降级配置（通义千问）
        self.fallback_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.fallback_model = "qwen-turbo"
        self.fallback_api_key = ""  # 需要用户在 .env 中设置
        self._using_fallback = False
        # 实例级失败计数（避免多用户并发问题）
        self._consecutive_failures: int = 0
        # per-session 对话历史（session_id → messages list）
        self._session_history: dict[str, list[dict]] = {}
        self._max_history: int = 10  # 每个会话保留最近 10 轮

    async def chat(self, query: str, context: str | None = None, session_id: str = "default") -> str | None:
        """生成回答，自动降级，支持多轮对话。

        链路：Dify RAG → DeepSeek → 通义千问

        Args:
            query: 用户输入文本
            context: 可选的 RAG 检索上下文（未接入 Dify 时使用）
            session_id: 会话 ID，用于多轮对话历史

        Returns:
            回答文本或 None
        """
        # 阶段 1：优先尝试 Dify RAG（仅 API Key 已配置时）
        if self._dify_configured():
            reply = await self._dify_or_fallback(query, session_id)
            if reply:
                return reply
            logger.info("[ChatBot] Dify 不可用，降级至直连 DeepSeek")

        # 阶段 2：原有 DeepSeek → 通义千问逻辑
        if self._consecutive_failures >= _FALLBACK_THRESHOLD:
            logger.warning("[ChatBot] 已达降级阈值，切换到通义千问")
            return await self._chat_fallback(query, context, session_id)

        try:
            client = self._create_client(self.primary_api_key, self.primary_base_url)
            messages = self._build_messages(query, context, session_id)

            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
                timeout=30,
            )
            reply = response.choices[0].message.content
            if reply:
                self._consecutive_failures = 0
                self._add_history(session_id, query, reply)
                logger.info(
                    "[ChatBot] DeepSeek 回答成功 (tokens=%d)",
                    response.usage.total_tokens if response.usage else 0,
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
                return await self._chat_fallback(query, context, session_id)
            return None

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
        try:
            client = self._create_client(self.fallback_api_key, self.fallback_base_url)
            messages = self._build_messages(query, context, session_id)
            response = await client.chat.completions.create(
                model=self.fallback_model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
                timeout=30,
            )
            reply = response.choices[0].message.content
            if reply:
                self._add_history(session_id, query, reply)
                logger.info("[ChatBot] 通义千问回答成功")
            return reply
        except Exception as e:
            logger.error("[ChatBot] 通义千问也失败: %s", e, exc_info=True)
            return None

    def _build_messages(self, query: str, context: str | None = None, session_id: str = "default") -> list[dict]:
        """构建消息数组（含多轮历史）。

        Args:
            query: 用户输入
            context: 可选的系统上下文
            session_id: 会话 ID

        Returns:
            消息列表（system + history + user）
        """
        messages: list[dict] = []
        if context:
            messages.append({"role": "system", "content": context})
        # 追加历史对话（最多保留 _max_history 轮）
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
        """清除指定会话的历史记录。

        Args:
            session_id: 会话 ID
        """
        self._session_history.pop(session_id, None)
        logger.info("[ChatBot] 已清除会话 %s 的历史", session_id)

    def set_fallback_api_key(self, api_key: str) -> None:
        """设置降级 API Key。"""
        self.fallback_api_key = api_key
        logger.info("[ChatBot] 通义千问 API Key 已设置")

    @property
    def using_fallback(self) -> bool:
        """当前是否使用降级方案。"""
        return self._using_fallback


chatbot = ChatBot()
