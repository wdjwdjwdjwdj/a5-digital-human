"""Edge-TTS 及降级 TTS 服务封装。

多级降级链路：Edge-TTS → Kokoro → pyttsx3
"""

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

from backend.config import settings

logger = logging.getLogger(__name__)


class RealtimeTTSManager:
    """语音合成管理器，支持多引擎自动降级。

    引擎优先级（不可调整）：
    1. Edge-TTS（云端，高音质）
    2. Kokoro（开源神经网络，中等音质，需 PyTorch）
    3. pyttsx3（离线，低音质，兜底）
    """

    def __init__(self) -> None:
        self.voice: str = settings.tts_voice
        self._kokoro_available: bool | None = None
        self._kokoro_pipeline = None

    # ── 公开接口 ────────────────────────────────────────────

    async def synthesize(self, text: str) -> bytes | None:
        """合成语音，引擎自动降级。

        Args:
            text: 要合成的文本

        Returns:
            音频字节流，None 表示全部失败
        """
        # 引擎 1：Edge-TTS
        audio = await self._try_edge_tts(text)
        if audio is not None:
            return audio

        # 引擎 2：Kokoro
        audio = await self._try_kokoro(text)
        if audio is not None:
            return audio

        # 引擎 3：pyttsx3（兜底）
        return self._try_pyttsx3(text)

    async def stream_synthesize(self, text: str):
        """流式合成语音，逐 chunk 产出音频字节。

        仅 Edge-TTS 支持流式产出；降级引擎返回单一 chunk。

        Args:
            text: 要合成的文本

        Yields:
            音频字节片段
        """
        try:
            from edge_tts import Communicate

            communicate = Communicate(text, self.voice)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
            return
        except ImportError:
            logger.warning("[TTS] edge-tts 未安装")
        except Exception as e:
            logger.warning("[TTS] Edge-TTS 流式失败: %s", e)

        # 降级：Kokoro
        audio = await self._try_kokoro(text)
        if audio is not None:
            yield audio
            return

        # 兜底：pyttsx3
        audio = self._try_pyttsx3(text)
        if audio is not None:
            yield audio

    # ── 引擎 1：Edge-TTS ───────────────────────────────────

    async def _try_edge_tts(self, text: str) -> bytes | None:
        """Edge-TTS 合成。

        Args:
            text: 要合成的文本

        Returns:
            音频字节流或 None
        """
        try:
            from edge_tts import Communicate

            communicate = Communicate(text, self.voice)
            audio = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio += chunk["data"]
            if audio:
                logger.info("[TTS] Edge-TTS 合成成功，大小=%d 字节", len(audio))
                return audio
            logger.warning("[TTS] Edge-TTS 返回空音频")
            return None
        except ImportError:
            logger.warning("[TTS] edge-tts 未安装")
            return None
        except Exception as e:
            logger.error("[TTS] Edge-TTS 合成失败: %s", e, exc_info=True)
            return None

    # ── 引擎 2：Kokoro ─────────────────────────────────────

    async def _try_kokoro(self, text: str) -> bytes | None:
        """Kokoro TTS 合成。

        需预先安装 kokoro 包（pip install kokoro）。
        首次调用时延迟加载模型。

        Args:
            text: 要合成的文本

        Returns:
            WAV 音频字节流或 None
        """
        pipeline = self._load_kokoro()
        if pipeline is None:
            return None

        try:
            import numpy as np
            from scipy.io.wavfile import write as write_wav

            generator = pipeline(text, voice="af_heart")
            audio_chunks: list[np.ndarray] = []
            for audio_array, _ in generator:
                audio_chunks.append(audio_array)

            if not audio_chunks:
                logger.warning("[TTS] Kokoro 返回空音频")
                return None

            full_audio = np.concatenate(audio_chunks)

            with NamedTemporaryFile(suffix=".wav", delete=False) as _tmp:
                _tmp.close()
                tmp_path = _tmp.name
            write_wav(tmp_path, 24000, full_audio.astype(np.float32))
            audio_bytes = Path(tmp_path).read_bytes()
            Path(tmp_path).unlink(missing_ok=True)
            logger.info("[TTS] Kokoro 合成成功，大小=%d 字节", len(audio_bytes))
            return audio_bytes
        except Exception as e:
            logger.error("[TTS] Kokoro 合成失败: %s", e, exc_info=True)
            return None

    def _load_kokoro(self) -> object | None:
        """延迟加载 Kokoro 模型。

        Returns:
            KPipeline 实例或 None
        """
        if self._kokoro_available is False:
            return None
        if self._kokoro_pipeline is not None:
            return self._kokoro_pipeline
        try:
            from kokoro import KPipeline

            self._kokoro_pipeline = KPipeline(lang_code="z")
            self._kokoro_available = True
            logger.info("[TTS] Kokoro 模型加载成功")
            return self._kokoro_pipeline
        except ImportError:
            logger.info("[TTS] kokoro 未安装，跳过")
            self._kokoro_available = False
            return None
        except Exception as e:
            logger.warning("[TTS] Kokoro 加载失败: %s", e)
            self._kokoro_available = False
            return None

    # ── 引擎 3：pyttsx3（兜底）─────────────────────────────

    @staticmethod
    def _try_pyttsx3(text: str) -> bytes | None:
        """pyttsx3 离线 TTS 合成。

        Args:
            text: 要合成的文本

        Returns:
            WAV 音频字节流或 None
        """
        try:
            import pyttsx3

            engine = pyttsx3.init()
            with NamedTemporaryFile(suffix=".wav", delete=False) as _tmp:
                _tmp.close()
                tmp_path = _tmp.name
            engine.save_to_file(text, tmp_path)
            engine.runAndWait()
            audio = Path(tmp_path).read_bytes()
            Path(tmp_path).unlink(missing_ok=True)
            logger.info("[TTS] pyttsx3 降级合成成功，大小=%d 字节", len(audio))
            return audio
        except Exception as e:
            logger.error("[TTS] pyttsx3 降级也失败: %s", e, exc_info=True)
            return None


# 向后兼容：旧代码可继续使用 TTSManager
TTSManager = RealtimeTTSManager

tts_manager = RealtimeTTSManager()
