"""Streamlit 管理后台主入口。

侧边栏 radio 导航，条件导入对应页面模块。
"""

import streamlit as st

st.set_page_config(
    page_title="景区数字人管理后台",
    page_icon="🏔️",
    layout="wide",
)

# ── 侧边栏导航 ─────────────────────────────────────────────
st.sidebar.title("🏔️ A5 景区导览")
st.sidebar.markdown("### AI 数字人管理后台")

PAGES = {
    "知识库管理": "knowledge",
    "数据大屏": "stats",
    "系统设置": "settings",
}

selected_page = st.sidebar.radio(
    "导航菜单",
    options=list(PAGES.keys()),
    index=0,
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.caption(f"当前页面: **{selected_page}**")
st.sidebar.caption("第十五届中国软件杯 · A5 赛题")

# ── 页面加载 ───────────────────────────────────────────────
page_key = PAGES[selected_page]

if page_key == "knowledge":
    from admin.pages.knowledge import render_page

    render_page()
elif page_key == "stats":
    from admin.pages.stats import render_page

    render_page()
elif page_key == "settings":
    from admin.pages.settings import render_page

    render_page()
