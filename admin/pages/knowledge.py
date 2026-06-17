"""知识库管理页面：上传文档、查看列表与上传历史。"""

import logging

import streamlit as st

from admin.utils.dify_admin import dify_admin

logger = logging.getLogger(__name__)

# 支持的文件类型
_ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def render_page() -> None:
    """渲染知识库管理页面。"""
    st.title("📚 知识库管理")
    st.markdown("上传景区文档到 Dify 知识库，提升 AI 回答准确率。")

    # ── 检查 Dify 配置 ─────────────────────────────────────
    if not dify_admin.api_key or dify_admin.api_key in ("", "your-key-here"):
        st.warning("⚠️ Dify API Key 未配置，请在 `.env` 文件中设置 `DIFY_API_KEY`。")
        return

    if not dify_admin.base_url or "localhost" in dify_admin.base_url:
        st.info(f"ℹ️ Dify 服务地址: {dify_admin.base_url}")
        st.caption("请确保 Dify 服务已启动（`cd dify/docker && docker compose up -d`）")

    # ── 文件上传区 ─────────────────────────────────────────
    st.subheader("📤 上传文档")
    uploaded_file = st.file_uploader(
        "选择文件",
        type=["md", "txt", "pdf"],
        help="支持 .md、.txt、.pdf 格式，单文件不超过 20MB",
    )

    if uploaded_file is not None:
        # 文件大小校验
        if uploaded_file.size > _MAX_FILE_SIZE:
            st.error(f"文件过大（{uploaded_file.size / 1024 / 1024:.1f}MB），请上传不超过 20MB 的文件。")
        else:
            # 扩展名校验
            ext = f".{uploaded_file.name.split('.')[-1].lower()}"
            if ext not in _ALLOWED_EXTENSIONS:
                st.error(f"不支持的文件类型 `{ext}`，请上传 .md / .txt / .pdf 文件。")
            else:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.info(f"📄 **{uploaded_file.name}** ({uploaded_file.size / 1024:.1f} KB)")
                with col2:
                    if st.button("🚀 上传到知识库", type="primary", use_container_width=True):
                        with st.spinner("正在上传到 Dify 知识库..."):
                            file_bytes = uploaded_file.getvalue()
                            result = dify_admin.upload_document(file_bytes, uploaded_file.name)
                        if result:
                            st.success(f"✅ `{uploaded_file.name}` 上传成功！")
                            st.rerun()
                        else:
                            st.error("上传失败，请检查 Dify 服务状态和配置。")

    st.divider()

    # ── 当前文档列表 ───────────────────────────────────────
    st.subheader("📋 知识库文档列表")
    with st.spinner("正在获取文档列表..."):
        documents = dify_admin.get_document_list()

    if documents:
        doc_data = []
        for doc in documents:
            doc_data.append(
                {
                    "文件名": doc.get("name", doc.get("filename", "未知")),
                    "大小": _format_size(doc.get("size", 0)),
                    "状态": doc.get("status", "未知"),
                    "创建时间": doc.get("created_at", doc.get("created_at", "")),
                }
            )
        st.dataframe(doc_data, use_container_width=True, hide_index=True)
    else:
        st.caption("暂无文档。请上传 .md / .txt / .pdf 文件到知识库。")

    st.divider()

    # ── 上传历史 ───────────────────────────────────────────
    st.subheader("🕐 最近上传记录")
    history = dify_admin.get_upload_history(limit=10)
    if history:
        hist_data = []
        for h in history:
            hist_data.append(
                {
                    "文件名": h["filename"],
                    "大小": _format_size(h["filesize"]),
                    "状态": "✅ 成功" if h["status"] == "success" else "❌ 失败",
                    "详情": h["detail"] or "-",
                    "时间": h["created_at"],
                }
            )
        st.dataframe(hist_data, use_container_width=True, hide_index=True)
    else:
        st.caption("暂无上传记录。")


def _format_size(size_bytes: int) -> str:
    """格式化文件大小。

    Args:
        size_bytes: 文件字节数

    Returns:
        可读的大小字符串
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
