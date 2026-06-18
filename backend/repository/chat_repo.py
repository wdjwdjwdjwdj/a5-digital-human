"""对话记录持久化 Repository。"""

import logging
import sqlite3
from pathlib import Path

from backend.config import settings

logger = logging.getLogger(__name__)

_DB_PATH = Path(settings.database_url.replace("sqlite:///", "").replace("./", ""))


class ChatRepository:
    """对话记录 CRUD，SQLite 参数化查询。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path:
            self._db_path = Path(db_path)
        else:
            self._db_path = _DB_PATH
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """确保表结构存在。"""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    reply TEXT NOT NULL,
                    provider TEXT DEFAULT 'deepseek',
                    satisfaction INTEGER DEFAULT NULL,
                    session_id TEXT DEFAULT 'default',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error("创建 conversations 表失败: %s", e)

    def save_conversation(
        self,
        query: str,
        reply: str,
        provider: str = "deepseek",
        session_id: str = "default",
    ) -> int | None:
        """保存一条对话记录。

        Args:
            query: 用户问题
            reply: AI 回答
            provider: LLM 提供商标识
            session_id: 会话 ID

        Returns:
            记录 ID 或 None
        """
        try:
            conn = sqlite3.connect(str(self._db_path))
            cursor = conn.execute(
                "INSERT INTO conversations (query, reply, provider, session_id) VALUES (?, ?, ?, ?)",
                (query, reply, provider, session_id),
            )
            conn.commit()
            record_id = cursor.lastrowid
            conn.close()
            logger.info("[ChatRepo] 对话已保存: id=%s", record_id)
            return record_id
        except sqlite3.Error as e:
            logger.error("[ChatRepo] 保存对话失败: %s", e)
            return None

    def get_history(self, session_id: str = "default", limit: int = 10) -> list[dict]:
        """获取会话历史记录。

        Args:
            session_id: 会话 ID
            limit: 返回条数

        Returns:
            对话记录列表
        """
        try:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT query, reply, provider, created_at FROM conversations "
                "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return rows
        except sqlite3.Error as e:
            logger.error("[ChatRepo] 查询历史失败: %s", e)
            return []


chat_repo = ChatRepository()
