"""管理后台 Dify API 封装。"""

import logging

from httpx import AsyncClient, HTTPError

from backend.config import settings

logger = logging.getLogger(__name__)


class DifyAdminClient:
    """Dify 管理 API 客户端。"""

    def __init__(self) -> None:
        self.base_url = settings.dify_api_url
        self.api_key = settings.dify_api_key

    async def upload_document(self, file_path: str) -> dict | None:
        """上传文档到知识库。

        Args:
            file_path: 本地文件路径

        Returns:
            上传结果或 None
        """
        url = f"{self.base_url}/datasets/{settings.dify_knowledge_base_id}/document/create-by-file"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with AsyncClient() as client:
                with open(file_path, "rb") as f:
                    files = {"file": f}
                    resp = await client.post(url, headers=headers, files=files, timeout=60.0)
                    resp.raise_for_status()
                    return resp.json()
        except (HTTPError, FileNotFoundError) as e:
            logger.error("[DifyAdmin] 上传文档失败: %s", e, exc_info=True)
            return None


dify_admin = DifyAdminClient()
