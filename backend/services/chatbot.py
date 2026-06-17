"""对话编排：LLM + RAG + 上下文管理。"""

import logging

from backend.config import settings

logger = logging.getLogger(__name__)

_FALLBACK_THRESHOLD: int = 3


class ChatBot:
    """对话引擎，负责编排 LLM 与 RAG 检索。

    主方案：DeepSeek API（通过 OpenAI 兼容接口）
    降级方案：通义千问 API（连续 3 次 5xx 时自动切换）
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

    async def chat(self, query: str, context: str | None = None) -> str | None:
        """生成回答，自动降级。

        Args:
            query: 用户输入文本
            context: 可选的 RAG 检索上下文（景区知识）

        Returns:
            回答文本或 None
        """
        if self._consecutive_failures >= _FALLBACK_THRESHOLD:
            logger.warning("[ChatBot] 已达降级阈值，切换到通义千问")
            return await self._chat_fallback(query, context)

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=self.primary_api_key,
                base_url=self.primary_base_url,
            )
            messages = self._build_messages(query, context)

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
                return await self._chat_fallback(query, context)
            return None

    async def _chat_fallback(self, query: str, context: str | None = None) -> str | None:
        """降级方案：通义千问 API。

        Args:
            query: 用户输入
            context: 可选的上下文

        Returns:
            回答文本或 None
        """
        if not self.fallback_api_key:
            logger.error("[ChatBot] 通义千问 API Key 未配置，降级不可用")
            return None
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=self.fallback_api_key,
                base_url=self.fallback_base_url,
            )
            messages = self._build_messages(query, context)
            response = await client.chat.completions.create(
                model=self.fallback_model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
                timeout=30,
            )
            reply = response.choices[0].message.content
            logger.info("[ChatBot] 通义千问回答成功")
            return reply
        except Exception as e:
            logger.error("[ChatBot] 通义千问也失败: %s", e, exc_info=True)
            return None

    @staticmethod
    def _build_messages(query: str, context: str | None = None) -> list[dict]:
        """构建消息数组。

        Args:
            query: 用户输入
            context: 可选的系统上下文

        Returns:
            消息列表
        """
        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": query})
        return messages

    def set_fallback_api_key(self, api_key: str) -> None:
        """设置降级 API Key。"""
        self.fallback_api_key = api_key
        logger.info("[ChatBot] 通义千问 API Key 已设置")

    @property
    def using_fallback(self) -> bool:
        """当前是否使用降级方案。"""
        return self._using_fallback


chatbot = ChatBot()
