"""Edge-TTS 及降级 TTS 服务封装。"""

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

from backend.config import settings

logger = logging.getLogger(__name__)


class TTSManager:
    """语音合成管理器，支持 Edge-TTS → pyttsx3 降级。"""

    def __init__(self) -> None:
        self.provider: str = settings.tts_provider
        self.voice: str = settings.tts_voice

    async def synthesize(self, text: str) -> bytes | None:
        """合成语音（主方案）。

        Args:
            text: 要合成的文本

        Returns:
            音频字节流，None 表示失败
        """
        try:
            from edge_tts import Communicate

            communicate = Communicate(text, self.voice)
            audio = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio += chunk["data"]
            if not audio:
                logger.warning("[TTS] Edge-TTS 返回空音频")
                return self.fallback(text)
            logger.info("[TTS] Edge-TTS 合成成功，大小=%d 字节", len(audio))
            return audio
        except Exception as e:
            logger.error("[TTS] Edge-TTS 合成失败: %s", e, exc_info=True)
            return self.fallback(text)

    def fallback(self, text: str) -> bytes | None:
        """降级方案：pyttsx3 离线 TTS。

        Args:
            text: 要合成的文本

        Returns:
            音频字节流或 None
        """
        try:
            import pyttsx3

            engine = pyttsx3.init()
            with NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            engine.save_to_file(text, tmp_path)
            engine.runAndWait()
            audio = Path(tmp_path).read_bytes()
            Path(tmp_path).unlink(missing_ok=True)
            logger.info("[TTS] pyttsx3 降级合成成功，大小=%d 字节", len(audio))
            return audio
        except Exception as e:
            logger.error("[TTS] pyttsx3 降级也失败: %s", e, exc_info=True)
            return None


tts_manager = TTSManager()
