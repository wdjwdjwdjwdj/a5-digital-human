"""数据大屏页面：对话统计、热门问题、趋势分析。"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

from backend.config import settings
from backend.repository.chat_repo import chat_repo

logger = logging.getLogger(__name__)

# 从配置统一读取数据库路径，避免硬编码
_DB_PATH = Path(settings.database_url.replace("sqlite:///", "").lstrip("./"))


def render_page() -> None:
    """渲染数据大屏页面。"""
    st.title("🏔️ 灵山胜境 · 数据大屏")
    st.markdown("对话数据统计与分析概览。")

    # ── 灵山主题 CSS ──────────────────────────────────────
    st.markdown("""
    <style>
        .stApp header { background-color: #2B5F75 !important; }
        div[data-testid="stMetricValue"] { color: #2B5F75 !important; font-weight: 700 !important; }
        div[data-testid="stMetricLabel"] { color: #1A3A4A !important; }
        .st-emotion-cache-1wivap2 { color: #C73E3A !important; }
        h1, h2, h3 { color: #2B5F75 !important; }
        section[data-testid="stSidebar"] { background: #1A3A4A !important; }
        section[data-testid="stSidebar"] * { color: #FFFFFF !important; }
    </style>
    """, unsafe_allow_html=True)

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

    # ── 游客感受度报告 ─────────────────────────────────────
    st.divider()
    st.subheader("😊 游客感受度分析")

    if _DB_PATH.exists():
        # 整体情感分布
        sentiment = asyncio.run(chat_repo.get_overall_sentiment())
        total_sentiment = sentiment["positive"] + sentiment["neutral"] + sentiment["negative"]
        if total_sentiment > 0:
            sat_col1, sat_col2 = st.columns([1, 2])
            with sat_col1:
                st.caption("情感分布")
                sat_data = {
                    "情感": ["积极 😊", "中性 😐", "消极 😟"],
                    "占比": [
                        round(sentiment["positive"] / total_sentiment * 100, 1),
                        round(sentiment["neutral"] / total_sentiment * 100, 1),
                        round(sentiment["negative"] / total_sentiment * 100, 1),
                    ],
                }
                st.bar_chart(sat_data, x="情感", y="占比", color=["#2B5F75", "#F5F0E8", "#C73E3A"])
            with sat_col2:
                st.caption(f"共 {total_sentiment} 条有情感标签的对话")
                st.metric("积极", sentiment["positive"], delta=None)
                st.metric("中性", sentiment["neutral"], delta=None)
                st.metric("消极", sentiment["negative"], delta=None)
        else:
            st.info("⏳ 暂无情感标签数据，开始对话后自动采集。")

        # 情感趋势折线图
        st.subheader("📈 情感趋势（近 7 日）")
        trend = asyncio.run(chat_repo.get_sentiment_trend(days=7))
        if trend and any(t["total"] > 0 for t in trend):
            trend_data = {
                "日期": [t["date"][5:] for t in trend],
                "积极": [t["positive"] for t in trend],
                "中性": [t["neutral"] for t in trend],
                "消极": [t["negative"] for t in trend],
            }
            st.line_chart(trend_data, x="日期", y=["积极", "中性", "消极"], color=["#2B5F75", "#4A8FA8", "#C73E3A"])
        else:
            st.caption("暂无情感趋势数据")

        # 关注热点（含情感评分）
        st.subheader("🔥 关注热点（情感排名）")
        hot = asyncio.run(chat_repo.get_hot_topics(limit=10))
        if hot:
            hot_data = []
            for h in hot:
                sentiment_label = (
                    "积极" if h["avg_satisfaction"] >= 2.5 else ("中性" if h["avg_satisfaction"] >= 1.5 else "消极")
                )
                hot_data.append(
                    {
                        "问题": h["query"][:25] + ("..." if len(h["query"]) > 25 else ""),
                        "频次": h["count"],
                        "平均情感分": h["avg_satisfaction"],
                        "情感倾向": sentiment_label,
                    }
                )
            st.dataframe(hot_data, use_container_width=True, hide_index=True)
        else:
            st.caption("暂无关注热点数据")

        # 服务改进建议
        st.subheader("💡 服务改进建议")
        suggestions = asyncio.run(chat_repo.get_service_suggestions(limit=5))
        if suggestions:
            for s in suggestions:
                st.warning(
                    f"**「{s['query'][:40]}」** — "
                    f"消极反馈 {s['negative_count']}/{s['total_count']} 次\n\n"
                    f"{s['suggestion']}"
                )
        else:
            st.caption("暂无服务改进建议，当前所有话题反馈良好 👍")
    else:
        st.info("💡 尚无对话数据，开始对话后将自动生成感受度报告。")

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
    asyncio.run(chat_repo.ensure_tables())


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
