"""ASR / VRM 模型预下载脚本。"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _out(msg: str) -> None:
    """输出到终端。"""
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def download_asr_model() -> bool:
    """下载 FunASR 模型。

    Returns:
        是否成功
    """
    try:
        from funasr import AutoModel

        AutoModel(model="paraformer-zh", device="cpu")
        _out("[OK] FunASR paraformer-zh 模型下载完成")
        return True
    except Exception as e:
        logger.error("[FAIL] FunASR 模型下载失败: %s", e, exc_info=True)
        return False


def download_vrm_model() -> bool:
    """下载 VRM 3D 模型。

    Returns:
        是否成功
    """
    import requests

    vrm_path = Path("frontend/static/vrm") / "AliciaSolid.vrm"
    if vrm_path.exists():
        _out(f"[OK] VRM 模型已存在: {vrm_path}")
        return True
    url = "https://github.com/vrm-c/UniVRM/raw/master/Tests/Models/Alicia_vrm-0.51/AliciaSolid_vrm-0.51.vrm"
    _out(f"[INFO] 正在下载 VRM 模型: {url}")
    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        vrm_path.write_bytes(resp.content)
        _out(f"[OK] VRM 模型下载完成: {vrm_path} ({len(resp.content) // 1024}KB)")
        return True
    except Exception as e:
        logger.error("[FAIL] VRM 模型下载失败: %s", e, exc_info=True)
        _out("[INFO] 请手动将 .vrm 文件放置到 frontend/static/vrm/ 目录")
        return False


if __name__ == "__main__":
    from pathlib import Path

    download_asr_model()
    download_vrm_model()
