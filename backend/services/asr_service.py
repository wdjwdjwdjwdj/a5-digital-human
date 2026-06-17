"""FunASR 语音识别封装，支持 Web Speech API 降级。"""

import logging

from backend.config import settings

logger = logging.getLogger(__name__)


class ASRManager:
    """语音识别管理器（服务端 FunASR，Web Speech 降级在浏览器端实现）。"""

    def __init__(self) -> None:
        self.provider: str = settings.asr_provider
        self.model_name: str = "paraformer-zh"
        self._model = None  # lazy load

    def _load_model(self) -> object | None:
        """延迟加载 FunASR 模型。"""
        if self._model is not None:
            return self._model
        try:
            from funasr import AutoModel

            self._model = AutoModel(
                model=self.model_name,
                device="cpu",
                vad=True,
            )
            logger.info("[ASR] FunASR 模型加载成功")
            return self._model
        except Exception as e:
            logger.error("[ASR] FunASR 模型加载失败: %s", e, exc_info=True)
            return None

    def transcribe(self, audio_path: str) -> str | None:
        """使用 FunASR 转写音频文件。

        Args:
            audio_path: 音频文件路径

        Returns:
            识别文本或 None
        """
        model = self._load_model()
        if model is None:
            logger.warning("[ASR] FunASR 不可用，返回 None")
            return None
        try:
            result = model.generate(input=audio_path)
            text = result[0].get("text", "") if result else ""
            if text:
                logger.info("[ASR] 识别成功: %s", text[:50])
                return text
            logger.warning("[ASR] 识别结果为空")
            return None
        except Exception as e:
            logger.error("[ASR] FunASR 识别失败: %s", e, exc_info=True)
            return None

    def unload_model(self) -> None:
        """卸载 ASR 模型释放内存。"""
        self._model = None
        logger.info("[ASR] 模型已卸载")


asr_manager = ASRManager()
