"""Streamlit 管理后台主入口。"""

import streamlit as st

st.set_page_config(
    page_title="A5 景区导览管理后台",
    page_icon="🏔️",
    layout="wide",
)

st.title("🏔️ A5 景区导览 AI 数字人")
st.markdown("### 管理后台")

st.sidebar.title("导航")
st.sidebar.page_link("app.py", label="首页")
st.sidebar.page_link("pages/knowledge.py", label="知识库管理")
st.sidebar.page_link("pages/stats.py", label="数据统计")
st.sidebar.page_link("pages/settings.py", label="系统设置")

st.info("请通过侧边栏导航选择功能页面。")
