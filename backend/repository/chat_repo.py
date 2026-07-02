"""对话记录持久化 Repository。"""

import asyncio
import logging
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from backend.config import settings

logger = logging.getLogger(__name__)

_DB_PATH = Path(settings.database_url.replace("sqlite:///", "").replace("./", ""))

_EMOTION_SATISFACTION_MAP: dict[str, int] = {
    "happy": 3,
    "surprise": 3,
    "neutral": 2,
    "sad": 1,
    "angry": 1,
}

_DB_TIMEOUT = 30.0


class ChatRepository:
    """对话记录 CRUD，SQLite 参数化查询。

    所有 public 方法均为 async，内部通过 asyncio.to_thread 将同步 sqlite3 调用
    迁移到线程池执行，释放事件循环。
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path:
            self._db_path = Path(db_path)
        else:
            self._db_path = _DB_PATH
        self._lock = threading.Lock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._tables_ensured = False  # 惰性初始化，首次 DB 操作时建表

    def _ensure_tables(self) -> None:
        """确保表结构存在（惰性初始化，双重检查锁）。"""
        if self._tables_ensured:
            return
        try:
            with self._lock:
                if self._tables_ensured:  # 双重检查避免竞态
                    return
                conn = sqlite3.connect(str(self._db_path))
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS conversations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            query TEXT NOT NULL,
                            reply TEXT NOT NULL,
                            provider TEXT DEFAULT 'deepseek',
                            satisfaction INTEGER DEFAULT NULL,
                            session_id TEXT DEFAULT 'default',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
                    self._tables_ensured = True
                finally:
                    conn.close()
        except sqlite3.Error as e:
            logger.error("创建 conversations 表失败: %s", e)

    async def ensure_tables(self) -> None:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._ensure_tables),
                timeout=_DB_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("[ChatRepo] ensure_tables 超时")

    async def save_conversation(
        self,
        query: str,
        reply: str,
        provider: str = "deepseek",
        session_id: str = "default",
        satisfaction: int | None = None,
    ) -> int | None:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self._sync_save_conversation,
                    query,
                    reply,
                    provider,
                    session_id,
                    satisfaction,
                ),
                timeout=_DB_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("[ChatRepo] save_conversation 超时")
            return None

    def _sync_save_conversation(
        self,
        query: str,
        reply: str,
        provider: str,
        session_id: str,
        satisfaction: int | None,
    ) -> int | None:
        try:
            with self._lock:
                conn = sqlite3.connect(str(self._db_path))
                try:
                    cursor = conn.execute(
                        "INSERT INTO conversations "
                        "(query, reply, provider, session_id, satisfaction) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (query, reply, provider, session_id, satisfaction),
                    )
                    record_id = cursor.lastrowid
                    conn.commit()
                finally:
                    conn.close()
            logger.info("[ChatRepo] 对话已保存: id=%s, satisfaction=%s", record_id, satisfaction)
            return record_id
        except sqlite3.Error as e:
            logger.error("[ChatRepo] 保存对话失败: %s", e)
            return None

    async def get_history(self, session_id: str = "default", limit: int = 10) -> list[dict]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._sync_get_history, session_id, limit),
                timeout=_DB_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("[ChatRepo] get_history 超时")
            return []

    def _sync_get_history(self, session_id: str, limit: int) -> list[dict]:
        try:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT query, reply, provider, created_at FROM conversations "
                    "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                    (session_id, limit),
                )
                rows = [dict(row) for row in cursor.fetchall()]
                return rows
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error("[ChatRepo] 查询历史失败: %s", e)
            return []

    async def get_overall_sentiment(self) -> dict[str, int]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._sync_get_overall_sentiment),
                timeout=_DB_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("[ChatRepo] get_overall_sentiment 超时")
            return {"positive": 0, "neutral": 0, "negative": 0}

    def _sync_get_overall_sentiment(self) -> dict[str, int]:
        try:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        SUM(CASE WHEN satisfaction = 3 THEN 1 ELSE 0 END) as positive,
                        SUM(CASE WHEN satisfaction = 2 THEN 1 ELSE 0 END) as neutral,
                        SUM(CASE WHEN satisfaction = 1 THEN 1 ELSE 0 END) as negative
                    FROM conversations
                    WHERE satisfaction IS NOT NULL
                """)
                row = cursor.fetchone()
                if row:
                    return {
                        "positive": row["positive"] or 0,
                        "neutral": row["neutral"] or 0,
                        "negative": row["negative"] or 0,
                    }
                return {"positive": 0, "neutral": 0, "negative": 0}
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error("[ChatRepo] 查询情感分布失败: %s", e)
            return {"positive": 0, "neutral": 0, "negative": 0}

    async def get_sentiment_trend(self, days: int = 7) -> list[dict]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._sync_get_sentiment_trend, days),
                timeout=_DB_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("[ChatRepo] get_sentiment_trend 超时")
            return []

    def _sync_get_sentiment_trend(self, days: int) -> list[dict]:
        try:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
                cursor.execute(
                    """
                    SELECT date(created_at) as date,
                           COUNT(*) as total,
                           SUM(CASE WHEN satisfaction = 3 THEN 1 ELSE 0 END) as positive,
                           SUM(CASE WHEN satisfaction = 2 THEN 1 ELSE 0 END) as neutral,
                           SUM(CASE WHEN satisfaction = 1 THEN 1 ELSE 0 END) as negative
                    FROM conversations
                    WHERE date(created_at) >= ?
                    GROUP BY date(created_at)
                    ORDER BY date ASC
                """,
                    (start_date,),
                )
                rows = [dict(row) for row in cursor.fetchall()]
                date_map = {r["date"]: r for r in rows}
                result: list[dict] = []
                for i in range(days):
                    day = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
                    if day in date_map:
                        result.append(date_map[day])
                    else:
                        result.append({"date": day, "total": 0, "positive": 0, "neutral": 0, "negative": 0})
                return result
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error("[ChatRepo] 查询情感趋势失败: %s", e)
            return []

    async def get_hot_topics(self, limit: int = 10) -> list[dict]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._sync_get_hot_topics, limit),
                timeout=_DB_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("[ChatRepo] get_hot_topics 超时")
            return []

    def _sync_get_hot_topics(self, limit: int) -> list[dict]:
        try:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT query, COUNT(*) as count,
                           ROUND(AVG(COALESCE(satisfaction, 2)), 2) as avg_satisfaction
                    FROM conversations
                    GROUP BY query
                    ORDER BY count DESC
                    LIMIT ?
                """,
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error("[ChatRepo] 查询热门话题失败: %s", e)
            return []

    async def get_service_suggestions(self, limit: int = 5) -> list[dict]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._sync_get_service_suggestions, limit),
                timeout=_DB_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error("[ChatRepo] get_service_suggestions 超时")
            return []

    def _sync_get_service_suggestions(self, limit: int) -> list[dict]:
        try:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT query,
                           COUNT(*) as total_count,
                           SUM(CASE WHEN satisfaction = 1 THEN 1 ELSE 0 END) as negative_count
                    FROM conversations
                    WHERE satisfaction IS NOT NULL
                    GROUP BY query
                    HAVING negative_count > 0
                    ORDER BY negative_count DESC, total_count DESC
                    LIMIT ?
                """,
                    (limit,),
                )
                rows = [dict(row) for row in cursor.fetchall()]
                for r in rows:
                    r["suggestion"] = (
                        f"游客对「{r['query'][:30]}」问题存在较多消极反馈，建议完善相关知识库内容或优化回答方式"
                    )
                return rows
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error("[ChatRepo] 查询服务建议失败: %s", e)
            return []


chat_repo = ChatRepository()
