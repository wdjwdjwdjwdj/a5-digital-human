"""ASR / Live2D 模型预下载脚本。"""

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


def download_live2d_model() -> bool:
    """下载 Live2D 模型（占位）。

    Returns:
        是否成功
    """
    # TODO: 从网络或本地资源复制 Live2D 模型
    _out("[INFO] Live2D 模型需手动放置到 frontend/static/live2d/")
    return True


if __name__ == "__main__":
    download_asr_model()
    download_live2d_model()
