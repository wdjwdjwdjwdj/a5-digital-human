"""SenseNova（日日新）API 客户端。

封装 OpenAI 兼容接口调用，包含：
- 5 秒超时控制（asyncio.wait_for 双重保障，符合比赛要求）
- 响应内容非空校验
- 流式/非流式双模式
- 完整的错误处理和日志

超时策略说明：
  sensenova-6.7-flash-lite 是推理模型（CoT），生成"推理过程→回答"两阶段。
  - 非流式 chat()：总超时 5s（比赛硬性要求）
  - 流式 chat_stream()：连接超时 5s，首 token 应 < 5s

系统提示词由调用方（chatbot.py）构建并传入，本客户端不修改消息内容。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from backend.config import settings
from backend.http_client import get_http_client

logger = logging.getLogger(__name__)

# ── 超时相关常量 ──────────────────────────────────────────
# 比赛要求：响应时间 < 5 秒，超时阈值 5 秒
_CHAT_TIMEOUT: float = 5.0      # 非流式总超时（比赛硬性要求）
_STREAM_TIMEOUT: float = 5.0    # 流式连接超时

# 系统提示词：由 chatbot.py 的 _build_messages() 方法构建，此处不再硬编码
# 原提示词（已删除）：
#   "你是灵山胜境景区的AI导览助手。请直接、简洁地回答用户问题，不要做冗长的推理分析。回答控制在100字以内。"
# 问题：该提示词未定义"灵灵"角色，导致回答不相关（牛头不对马嘴）


class SenseNovaResponse:
    """SenseNova 单次响应的结构化容器。"""

    __slots__ = ("content", "total_tokens", "latency_ms")

    def __init__(self, content: str, total_tokens: int = 0, latency_ms: float = 0.0) -> None:
        self.content = content
        self.total_tokens = total_tokens
        self.latency_ms = latency_ms

    @property
    def is_valid(self) -> bool:
        """响应是否有效（内容非空）。"""
        return bool(self.content and self.content.strip())


class SenseNovaClient:
    """SenseNova API 客户端。

    特性：
    - 5 秒超时（asyncio.wait_for 双重保障）
    - 响应内容非空强制校验
    - 流式/非流式双模式支持
    - 延迟统计

    Usage:
        client = SenseNovaClient()
        resp = await client.chat([{"role": "user", "content": "你好"}])
        if resp.is_valid:
            print(resp.content)
    """

    def __init__(self) -> None:
        api_key = settings.sensenova_api_key
        if not api_key:
            logger.warning("[SenseNova] API Key 未配置！请在 .env 中设置 SENSENOVA_API_KEY")

        self.model = settings.sensenova_model
        self._chat_timeout = _CHAT_TIMEOUT
        self._stream_timeout = _STREAM_TIMEOUT

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.sensenova_base_url,
            http_client=get_http_client(),
            timeout=self._chat_timeout,
        )
        logger.info(
            "[SenseNova] 客户端已初始化: model=%s, chat_timeout=%.1fs, stream_timeout=%.1fs",
            self.model,
            self._chat_timeout,
            self._stream_timeout,
        )

    # ═════════════════════════════════════════════════════════
    # 公共 API
    # ═════════════════════════════════════════════════════════

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> SenseNovaResponse:
        """发送非流式对话请求。

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            temperature: 生成温度 (0-2)
            max_tokens: 最大输出 Token 数

        Returns:
            SenseNovaResponse 实例；失败时 content 为空字符串
        """
        if not settings.sensenova_api_key:
            logger.error("[SenseNova] API Key 未配置，无法调用")
            return SenseNovaResponse("", 0, 0)

        start = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # 直接使用传入的消息（已由 chatbot.py 构建完整系统提示词）
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
                timeout=self._chat_timeout,
            )
            return self._validate(response, start)
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(
                "[SenseNova] 非流式请求超时 (阈值=%.1fs, 实际耗时=%.0fms)",
                self._chat_timeout,
                elapsed,
            )
            return SenseNovaResponse("", 0, elapsed)
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(
                "[SenseNova] 请求失败 (耗时=%.0fms): %s",
                elapsed,
                e,
                exc_info=True,
            )
            return SenseNovaResponse("", 0, elapsed)

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> AsyncGenerator[str, None]:
        """发送流式对话请求，逐 token yield。

        Args:
            messages: 消息列表
            temperature: 生成温度
            max_tokens: 最大输出 Token 数

        Yields:
            文本 token 片段
        """
        if not settings.sensenova_api_key:
            logger.error("[SenseNova] API Key 未配置，流式调用不可用")
            return

        start = time.monotonic()
        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,  # 直接使用传入的消息（已由 chatbot.py 构建完整系统提示词）
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                ),
                timeout=self._stream_timeout,
            )

            first_token = True
            async for chunk in response:
                if first_token:
                    first_token = False
                    ttft = (time.monotonic() - start) * 1000
                    logger.info("[SenseNova] 首 token 延迟: %.0fms", ttft)

                if chunk.choices and chunk.choices[0].delta:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield content

            total_elapsed = (time.monotonic() - start) * 1000
            logger.info("[SenseNova] 流式完成 (总耗时=%.0fms)", total_elapsed)

        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(
                "[SenseNova] 流式请求超时 (阈值=%.1fs, 耗时=%.0fms)",
                self._stream_timeout,
                elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.error(
                "[SenseNova] 流式请求失败 (耗时=%.0fms): %s",
                elapsed,
                e,
                exc_info=True,
            )

    # ═════════════════════════════════════════════════════════
    # 内部方法
    # ═════════════════════════════════════════════════════════

    def _validate(self, response, start_time: float) -> SenseNovaResponse:
        """验证并结构化 OpenAI 响应。

        校验规则：
        1. choices 非空
        2. message.content 非空非空白
        3. 提取 token 用量统计

        注意：sensenova-6.7-flash-lite 是推理模型，content 前可能有 \\n\\n 前缀。

        Args:
            response: OpenAI ChatCompletion 响应对象
            start_time: 请求开始时间（monotonic）

        Returns:
            SenseNovaResponse 实例
        """
        latency = (time.monotonic() - start_time) * 1000

        # 规则 1：choices 非空
        if not response.choices:
            logger.warning("[SenseNova] 响应无 choices（延迟=%.0fms）", latency)
            return SenseNovaResponse("", 0, latency)

        choice = response.choices[0]

        # 规则 2：message.content 非空非空白（推理模型 content 前可能有 \\n\\n）
        if not choice.message or not choice.message.content:
            logger.warning("[SenseNova] 响应 content 为空（延迟=%.0fms）", latency)
            return SenseNovaResponse("", 0, latency)

        content = choice.message.content.strip()
        if not content:
            logger.warning("[SenseNova] 响应 content 为纯空白（延迟=%.0fms）", latency)
            return SenseNovaResponse("", 0, latency)

        # 规则 3：提取 token 用量
        total_tokens = response.usage.total_tokens if response.usage else 0

        # 规则 4：延迟检查（超过 5s 告警但不阻断）
        _WARN_THRESHOLD_MS = 5000
        if latency > _WARN_THRESHOLD_MS:
            logger.warning(
                "[SenseNova] 响应延迟偏高 (建议<5s, 实际=%.0fms)",
                latency,
            )

        logger.info(
            "[SenseNova] 响应成功 (延迟=%.0fms, tokens=%d, 内容长度=%d)",
            latency,
            total_tokens,
            len(content),
        )
        return SenseNovaResponse(content, total_tokens, latency)


# ── 模块级单例 ───────────────────────────────────────────
sensenova = SenseNovaClient()
