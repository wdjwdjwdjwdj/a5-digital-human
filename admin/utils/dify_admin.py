"""管理后台 Dify API 封装。

提供知识库文档上传、列表查询、上传历史记录管理。
同步客户端实现，适配 Streamlit 运行环境。
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any

from httpx import Client, HTTPError, Timeout

from backend.config import settings

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/conversations.db")
_UPLOAD_TIMEOUT = 120.0


class DifyAdminClient:
    """Dify 管理 API 客户端（同步）。"""

    def __init__(self) -> None:
        self.base_url = settings.dify_api_url
        self.api_key = settings.dify_api_key
        self._init_db()

    # ── 数据库初始化 ────────────────────────────────────────

    @staticmethod
    def _init_db() -> None:
        """初始化上传记录表。"""
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(str(_DB_PATH))
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS upload_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    filesize INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'success',
                    detail TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error("数据库初始化失败: %s", e)

    # ── Dify API ────────────────────────────────────────────

    def upload_document(self, file_content: bytes, filename: str) -> dict | None:
        """上传文档到 Dify 知识库。

        Args:
            file_content: 文件二进制内容
            filename: 文件名（含扩展名）

        Returns:
            Dify API 响应或 None
        """
        if not self.api_key or self.api_key in ("", "your-key-here"):
            self._record_upload(filename, 0, "failed", "API Key 未配置")
            return None

        kb_id = settings.dify_knowledge_base_id
        if not kb_id:
            self._record_upload(filename, 0, "failed", "知识库 ID 未配置")
            return None

        url = f"{self.base_url}/datasets/{kb_id}/document/create-by-file"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            with Client(timeout=Timeout(_UPLOAD_TIMEOUT)) as client:
                files = {"file": (filename, file_content, self._guess_mime(filename))}
                resp = client.post(url, headers=headers, files=files)
                resp.raise_for_status()
                data = resp.json()
                self._record_upload(filename, len(file_content), "success")
                logger.info("[DifyAdmin] 文档上传成功: %s", filename)
                return data
        except HTTPError as e:
            msg = f"Dify API 错误: {e}"
            logger.error("[DifyAdmin] %s", msg)
            self._record_upload(filename, len(file_content), "failed", msg)
            return None
        except Exception as e:
            msg = f"上传异常: {e}"
            logger.error("[DifyAdmin] %s", msg, exc_info=True)
            self._record_upload(filename, len(file_content), "failed", msg)
            return None

    def get_document_list(self) -> list[dict[str, Any]]:
        """获取知识库文档列表。

        Returns:
            文档列表（含 id, name, size, created_at 等字段）
        """
        if not self.api_key or self.api_key in ("", "your-key-here"):
            return []

        kb_id = settings.dify_knowledge_base_id
        if not kb_id:
            return []

        url = f"{self.base_url}/datasets/{kb_id}/documents"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            with Client(timeout=Timeout(30.0)) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                documents = data.get("data", [])
                if not documents and "documents" in data:
                    documents = data["documents"]
                return documents
        except HTTPError as e:
            logger.error("[DifyAdmin] 获取文档列表失败: %s", e)
            return []
        except Exception as e:
            logger.error("[DifyAdmin] 获取文档列表异常: %s", e, exc_info=True)
            return []

    def get_upload_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取最近上传历史。

        Args:
            limit: 返回条数上限

        Returns:
            上传历史记录列表
        """
        try:
            conn = sqlite3.connect(str(_DB_PATH))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT id, filename, filesize, status, detail, created_at
                FROM upload_history
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except sqlite3.Error as e:
            logger.error("查询上传历史失败: %s", e)
            return []

    # ── 内部方法 ────────────────────────────────────────────

    def _record_upload(
        self,
        filename: str,
        filesize: int,
        status: str,
        detail: str = "",
    ) -> None:
        """记录上传历史到 SQLite。

        Args:
            filename: 文件名
            filesize: 文件大小（字节）
            status: 状态（success/failed）
            detail: 失败详情
        """
        try:
            conn = sqlite3.connect(str(_DB_PATH))
            conn.execute(
                "INSERT INTO upload_history (filename, filesize, status, detail) VALUES (?, ?, ?, ?)",
                (filename, filesize, status, detail),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error("记录上传历史失败: %s", e)

    @staticmethod
    def _guess_mime(filename: str) -> str:
        """根据扩展名猜测 MIME 类型。

        Args:
            filename: 文件名

        Returns:
            MIME 类型字符串
        """
        ext = Path(filename).suffix.lower()
        return {
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".html": "text/html",
            ".json": "application/json",
        }.get(ext, "application/octet-stream")


dify_admin = DifyAdminClient()
