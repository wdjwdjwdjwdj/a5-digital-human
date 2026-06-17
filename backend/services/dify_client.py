"""Dify 对话 API 封装。

双模设计：
- 主模式：连接 Dify 服务进行 RAG 对话
- 降级模式：Dify 不可用时返回 None，由上层切换直连 LLM
"""

import logging
from pathlib import Path

from httpx import AsyncClient, HTTPError

from backend.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT_CHAT: float = 30.0
_TIMEOUT_UPLOAD: float = 120.0


class DifyClient:
    """Dify 对话 API 客户端。"""

    def __init__(self) -> None:
        self.base_url = settings.dify_api_url
        self.api_key = settings.dify_api_key

    async def chat(
        self,
        query: str,
        user: str = "default",
        conversation_id: str | None = None,
    ) -> dict | None:
        """发送对话请求到 Dify API。

        Args:
            query: 用户输入文本
            user: 用户标识
            conversation_id: 对话 ID，传 None 表示新建对话

        Returns:
            Dify 响应内容或 None（失败时）
        """
        url = f"{self.base_url}/chat-messages"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "query": query,
            "user": user,
            "response_mode": "blocking",
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        try:
            async with AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=_TIMEOUT_CHAT)
                resp.raise_for_status()
                return resp.json()
        except HTTPError as e:
            logger.error("[DifyClient] 对话请求失败: %s", e)
            return None

    async def update_knowledge(self, file_path: str) -> dict | None:
        """上传文档到知识库。

        Args:
            file_path: 文档本地路径

        Returns:
            上传响应或 None（失败时）
        """
        url = f"{self.base_url}/datasets/{settings.dify_knowledge_base_id}/upload"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        fp = Path(file_path)
        if not fp.exists():
            logger.error("[DifyClient] 文档不存在: %s", file_path)
            return None

        try:
            async with AsyncClient() as client:
                with fp.open("rb") as f:
                    files = {"file": (fp.name, f, "application/octet-stream")}
                    resp = await client.post(url, headers=headers, files=files, timeout=_TIMEOUT_UPLOAD)
                    resp.raise_for_status()
                    logger.info("[DifyClient] 文档上传成功: %s", fp.name)
                    return resp.json()
        except Exception as e:
            logger.error("[DifyClient] 文档上传失败 (%s): %s", file_path, e)
            return None


dify_client = DifyClient()
