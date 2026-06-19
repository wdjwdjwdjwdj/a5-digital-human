"""系统设置页面：VRM 3D 模型、TTS 音色、系统状态。"""

import logging
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

from backend.config import settings

logger = logging.getLogger(__name__)

_VRM_DIR = Path("frontend/static/vrm")
_API_BASE = settings.api_base_url

_TTS_VOICES = {
    "zh-CN-XiaoxiaoNeural": "晓晓（女声，温柔）",
    "zh-CN-YunxiNeural": "云希（男声，阳光）",
    "zh-CN-XiaoyiNeural": "晓伊（女声，亲切）",
}


def render_page() -> None:
    """渲染系统设置页面。"""
    st.title("⚙️ 系统设置")
    st.markdown("管理数字人模型、语音配置与查看系统状态。")

    # ── VRM 3D 模型选择 ───────────────────────────────────
    st.subheader("🎭 VRM 3D 模型")
    models = _list_vrm_models()
    if models:
        current_model = settings.vrm_model_url
        default_index = 0
        model_labels = []
        for i, m in enumerate(models):
            label = m["name"]
            if m["path"] == current_model:
                label += " (当前)"
                default_index = i
            model_labels.append(label)

        selected_idx = st.selectbox(
            "选择 VRM 3D 模型",
            options=list(range(len(models))),
            format_func=lambda i: model_labels[i],
            index=default_index,
        )
        if st.button("应用模型", type="primary"):
            selected_model = models[selected_idx]
            with st.spinner("正在发送模型切换请求..."):
                success = _switch_vrm_model(selected_model["path"])
                if success:
                    st.success(f"✅ 已发送模型切换指令：{selected_model['name']}")
                    st.caption("前端将在 3 秒内热加载新模型")
                else:
                    st.error("❌ 模型切换失败，请检查数字人服务是否运行")
    else:
        st.warning("⚠️ 未检测到 VRM 模型文件，请将模型放置在 `frontend/static/vrm/` 目录下。")

    st.divider()

    # ── TTS 音色选择 ───────────────────────────────────────
    st.subheader("🔊 TTS 语音合成")
    st.caption(f"当前音色: {settings.tts_voice}")
    voice_options = list(_TTS_VOICES.keys())
    voice_labels = [f"{k} - {v}" for k, v in _TTS_VOICES.items()]
    default_voice_idx = 0
    for i, v in enumerate(voice_options):
        if v == settings.tts_voice:
            default_voice_idx = i
            break

    selected_voice = st.selectbox(
        "选择 TTS 音色",
        options=voice_options,
        format_func=lambda x: dict(zip(voice_options, voice_labels, strict=True))[x],
        index=default_voice_idx,
    )
    if st.button("试听音色", type="secondary"):
        st.info(f"已选择音色: {_TTS_VOICES.get(selected_voice, selected_voice)}")
        st.caption("提示：TTS 音色切换需在 `.env` 文件中修改 `TTS_VOICE` 配置。")

    st.divider()

    # ── 系统状态 ───────────────────────────────────────────
    st.subheader("🔌 系统状态")
    with st.spinner("正在检测各模块连通状态..."):
        status = _check_system_status()
    st.json(status)

    # 显示状态摘要
    all_ok = all(v.get("status") == "✅ 正常" for v in status.values())
    if all_ok:
        st.success("🎉 所有模块运行正常！")
    else:
        warnings = [k for k, v in status.items() if v.get("status") != "✅ 正常"]
        for w in warnings:
            st.warning(f"⚠️ **{w}**: {status[w].get('message', '异常')}")


def _list_vrm_models() -> list[dict[str, str]]:
    """扫描 VRM 模型目录。

    Returns:
        模型列表，每项包含 name 和 path
    """
    if not _VRM_DIR.exists():
        return []

    models = []
    for item in sorted(_VRM_DIR.iterdir()):
        if item.is_file() and item.suffix.lower() == ".vrm":
            models.append({"name": item.stem, "path": str(item.relative_to(_VRM_DIR))})
    return models


def _check_system_status() -> dict[str, dict[str, Any]]:
    """检测各模块连通状态。

    Returns:
        各模块状态字典
    """
    status: dict[str, dict[str, Any]] = {}

    # LLM (DeepSeek)
    if settings.deepseek_api_key and settings.deepseek_api_key not in ("", "your-key-here"):
        status["LLM (DeepSeek)"] = {"status": "✅ 正常", "message": "API Key 已配置"}
    else:
        status["LLM (DeepSeek)"] = {"status": "⚠️ 未配置", "message": "请设置 DEEPSEEK_API_KEY"}

    # Dify
    if settings.dify_api_key and settings.dify_api_key not in ("", "your-key-here"):
        dify_ok = _check_http_connectivity(settings.dify_api_url)
        if dify_ok:
            status["Dify RAG"] = {"status": "✅ 正常", "message": f"服务可达 ({settings.dify_api_url})"}
        else:
            status["Dify RAG"] = {"status": "⚠️ 不可达", "message": f"无法连接 {settings.dify_api_url}"}
    else:
        status["Dify RAG"] = {"status": "⚠️ 未配置", "message": "请设置 DIFY_API_KEY"}

    # Edge-TTS
    try:
        import edge_tts  # noqa: F401

        status["Edge-TTS"] = {"status": "✅ 正常", "message": f"音色: {settings.tts_voice}"}
    except ImportError:
        status["Edge-TTS"] = {"status": "⚠️ 未安装", "message": "请安装 edge-tts 包"}

    # VRM 3D
    vrm_models = _list_vrm_models()
    if vrm_models:
        status["VRM 3D"] = {"status": "✅ 正常", "message": f"发现 {len(vrm_models)} 个模型"}
    else:
        status["VRM 3D"] = {"status": "⚠️ 无模型", "message": "frontend/static/vrm/ 目录为空"}

    # FastAPI 服务
    fastapi_ok = _check_http_connectivity(f"{_API_BASE}/health")
    if fastapi_ok:
        status["FastAPI 服务"] = {"status": "✅ 正常", "message": "http://localhost:8000"}
    else:
        status["FastAPI 服务"] = {"status": "⚠️ 未启动", "message": "请运行 python main.py 启动"}

    return status


def _switch_vrm_model(model_path: str) -> bool:
    """调用后端 API 切换 VRM 3D 模型。

    Args:
        model_path: VRM 模型文件名（如 AliciaSolid.vrm）

    Returns:
        切换成功返回 True
    """
    try:
        resp = httpx.post(
            f"{_API_BASE}/api/vrm/model",
            json={"path": model_path},
            timeout=10.0,
        )
        result = resp.json()
        return result.get("success", False)
    except Exception as e:
        logger.error("[VRM] 模型切换请求失败: %s", e)
        return False


def _check_http_connectivity(url: str, timeout: float = 5.0) -> bool:
    """检测 HTTP 服务是否可达。

    Args:
        url: 服务地址
        timeout: 超时秒数

    Returns:
        可达返回 True
    """
    try:
        resp = httpx.get(url, timeout=timeout)
        return resp.is_success
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        return False
