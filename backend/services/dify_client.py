"""Dify 对话 API 封装。"""

import logging

from httpx import AsyncClient, HTTPError

from backend.config import settings

logger = logging.getLogger(__name__)


class DifyClient:
    """Dify 对话 API 客户端。"""

    def __init__(self) -> None:
        self.base_url = settings.dify_api_url
        self.api_key = settings.dify_api_key

    async def chat(self, query: str, user: str = "default") -> dict | None:
        """发送对话请求到 Dify API。

        Args:
            query: 用户输入文本
            user: 用户标识

        Returns:
            Dify 响应内容或 None（失败时）
        """
        url = f"{self.base_url}/chat-messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query,
            "user": user,
            "response_mode": "blocking",
        }
        try:
            async with AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=30.0)
                resp.raise_for_status()
                return resp.json()
        except HTTPError as e:
            logger.error("[DifyClient] 请求失败: %s", e, exc_info=True)
            return None


dify_client = DifyClient()
