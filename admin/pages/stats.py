"""数据大屏页面：对话统计、热门问题、趋势分析。"""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

from backend.repository.chat_repo import chat_repo

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/conversations.db")


def render_page() -> None:
    """渲染数据大屏页面。"""
    st.title("📊 数据大屏")
    st.markdown("对话数据统计与分析概览。")

    # ── 确保数据库和表存在 ─────────────────────────────────
    if not _DB_PATH.exists():
        st.info("💡 尚无对话数据。启动数字人服务并与 AI 对话后，统计数据将在此展示。")
        _render_empty_state()
        return

    _ensure_tables()

    try:
        stats = _load_stats()
    except (sqlite3.Error, Exception) as e:
        logger.error("加载统计数据失败: %s", e, exc_info=True)
        st.error("加载统计数据失败，请检查数据库连接。")
        _render_empty_state()
        return

    # ── 三个核心指标 ───────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="🗣️ 累计对话次数",
            value=stats["total_conversations"],
            delta=None,
        )
    with col2:
        st.metric(
            label="📅 今日对话",
            value=stats["today_conversations"],
            delta=stats["today_delta"],
        )
    with col3:
        satisfaction = stats["avg_satisfaction"]
        st.metric(
            label="⭐ 今日满意度",
            value=f"{satisfaction:.1f}" if satisfaction > 0 else "暂无数据",
            delta=None,
        )

    st.divider()

    # ── 双栏：热门问题 + 趋势 ──────────────────────────────
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("🔥 热门问题 Top 10")
        top_questions = stats.get("top_questions", [])
        if top_questions:
            chart_data = {
                "问题": [q["query"][:20] + ("..." if len(q["query"]) > 20 else "") for q in top_questions],
                "次数": [q["count"] for q in top_questions],
            }
            st.bar_chart(chart_data, x="问题", y="次数")
        else:
            st.caption("暂无数据")

    with chart_col2:
        st.subheader("📈 近 7 日对话趋势")
        daily_counts = stats.get("daily_counts", [])
        if daily_counts:
            chart_data = {
                "日期": [d["date"] for d in daily_counts],
                "对话次数": [d["count"] for d in daily_counts],
            }
            st.line_chart(chart_data, x="日期", y="对话次数")
        else:
            st.caption("暂无数据")

    # ── 详细表格 ───────────────────────────────────────────
    st.divider()
    st.subheader("📋 最近对话记录")
    recent = stats.get("recent_conversations", [])
    if recent:
        conv_data = []
        for c in recent:
            conv_data.append(
                {
                    "用户问题": c["query"][:50] + ("..." if len(c["query"]) > 50 else ""),
                    "AI 回答": c["reply"][:50] + ("..." if len(c["reply"]) > 50 else ""),
                    "LLM": c.get("provider", "deepseek"),
                    "时间": c["created_at"],
                }
            )
        st.dataframe(conv_data, use_container_width=True, hide_index=True)
    else:
        st.caption("暂无对话记录")


def _load_stats() -> dict[str, Any]:
    """从 SQLite 加载统计数据。

    Returns:
        包含各项统计数据的字典
    """
    stats: dict[str, Any] = {}

    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        seven_days_ago = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")

        # 累计对话次数
        cursor.execute("SELECT COUNT(*) as cnt FROM conversations")
        row = cursor.fetchone()
        stats["total_conversations"] = row["cnt"] if row else 0

        # 今日对话次数
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE date(created_at) = ?",
            (today,),
        )
        row = cursor.fetchone()
        stats["today_conversations"] = row["cnt"] if row else 0

        # 昨日对话次数（用于计算 delta）
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE date(created_at) = ?",
            (yesterday,),
        )
        row = cursor.fetchone()
        yesterday_count = row["cnt"] if row else 0
        stats["today_delta"] = stats["today_conversations"] - yesterday_count

        # 今日满意度（平均值）
        cursor.execute(
            """
            SELECT AVG(satisfaction) as avg_sat
            FROM conversations
            WHERE date(created_at) = ? AND satisfaction IS NOT NULL
            """,
            (today,),
        )
        row = cursor.fetchone()
        stats["avg_satisfaction"] = round(row["avg_sat"], 1) if row and row["avg_sat"] else 0.0

        # 热门问题 Top 10
        cursor.execute(
            """
            SELECT query, COUNT(*) as count
            FROM conversations
            GROUP BY query
            ORDER BY count DESC
            LIMIT 10
            """
        )
        stats["top_questions"] = [dict(row) for row in cursor.fetchall()]

        # 近 7 日对话趋势
        cursor.execute(
            """
            SELECT date(created_at) as date, COUNT(*) as count
            FROM conversations
            WHERE date(created_at) >= ?
            GROUP BY date(created_at)
            ORDER BY date ASC
            """,
            (seven_days_ago,),
        )
        daily = [dict(row) for row in cursor.fetchall()]

        # 填充缺失日期（补 0）
        date_counts = {d["date"]: d["count"] for d in daily}
        full_daily = []
        for i in range(7):
            day = (datetime.now() - timedelta(days=6 - i)).strftime("%Y-%m-%d")
            full_daily.append({"date": day, "count": date_counts.get(day, 0)})
        stats["daily_counts"] = full_daily

        # 最近 10 条对话记录
        cursor.execute(
            """
            SELECT query, reply, provider, created_at
            FROM conversations
            ORDER BY created_at DESC
            LIMIT 10
            """
        )
        stats["recent_conversations"] = [dict(row) for row in cursor.fetchall()]

    return stats


def _ensure_tables() -> None:
    """确保 conversations 表存在（委托给 chat_repo）。"""
    chat_repo.ensure_tables()


def _render_empty_state() -> None:
    """渲染无数据时的占位内容。"""
    cols = st.columns(3)
    for col in cols:
        with col:
            st.metric(label="🗣️ 累计对话次数", value=0)
            st.metric(label="📅 今日对话", value=0)
            st.metric(label="⭐ 今日满意度", value="暂无数据")
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.caption("热门问题 Top 10 — 暂无数据")
    with col2:
        st.caption("近 7 日对话趋势 — 暂无数据")
