"""FunASR 语音识别封装，支持 Web Speech API 降级 + Silero VAD 静音修剪。"""

import asyncio
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)


class VADManager:
    """Silero VAD 语音活动检测管理器。

    用于检测音频中的语音片段并修剪尾部静音，降低 ASR 处理时长。
    模型加载失败时静默降级，不影响主流程。
    """

    def __init__(self) -> None:
        self._model = None
        self._threshold: float = 0.3
        self._min_silence_duration_ms: int = 800

    def _load_model(self) -> Any | None:
        """延迟加载 Silero VAD 模型。

        Returns:
            VAD 模型实例或 None
        """
        if self._model is not None:
            return self._model
        try:
            import silero_vad

            self._model = silero_vad.load_silero_vad()
            logger.info("[VAD] Silero VAD 模型加载成功")
            return self._model
        except ImportError:
            logger.warning("[VAD] silero-vad 未安装，跳过 VAD")
            return None
        except Exception as e:
            logger.warning("[VAD] Silero VAD 加载失败: %s，跳过 VAD", e)
            return None

    def load_audio(self, audio_path: str) -> np.ndarray | None:
        """加载音频文件并转换为 16kHz 单声道 float32 数组。

        先用 scipy 尝试加载（WAV 格式），失败后用 pydub 尝试。

        Args:
            audio_path: 音频文件路径

        Returns:
            float32 numpy 数组（值域 [-1, 1]），或 None
        """
        audio = self._load_with_scipy(audio_path)
        if audio is not None:
            return audio
        return self._load_with_pydub(audio_path)

    def _load_with_scipy(self, audio_path: str) -> np.ndarray | None:
        """使用 scipy 加载 WAV 音频。

        Args:
            audio_path: 音频文件路径

        Returns:
            numpy 数组或 None
        """
        try:
            from scipy.io import wavfile

            sr, data = wavfile.read(audio_path)
            if data.ndim > 1:
                data = data.mean(axis=1)

            dtype_max = np.iinfo(data.dtype).max if np.issubdtype(data.dtype, np.integer) else 1.0
            data = data.astype(np.float32) / dtype_max

            if sr != 16000:
                from scipy import signal

                target_len = int(len(data) * 16000 / sr)
                data = signal.resample(data, target_len).astype(np.float32)
            return data
        except Exception as e:
            logger.debug("[VAD] scipy 读取失败: %s", e)
            return None

    def _load_with_pydub(self, audio_path: str) -> np.ndarray | None:
        """使用 pydub 加载音频（支持多种格式）。

        Args:
            audio_path: 音频文件路径

        Returns:
            numpy 数组或 None
        """
        try:
            import pydub

            audio = pydub.AudioSegment.from_file(audio_path)
            audio = audio.set_frame_rate(16000).set_channels(1)
            samples = np.array(audio.get_array_of_samples()).astype(np.float32) / 32768.0
            return samples
        except Exception as e:
            logger.warning("[VAD] pydub 读取也失败: %s，VAD 不可用", e)
            return None

    def detect_speech(self, audio_path: str) -> list[dict] | None:
        """检测音频中的语音片段。

        返回每个语音片段的起始和结束时间（秒）。
        VAD 不可用时返回 None。

        Args:
            audio_path: 音频文件路径

        Returns:
            语音片段列表 [{"start": float, "end": float}, ...] 或 None
        """
        model = self._load_model()
        if model is None:
            return None

        audio = self.load_audio(audio_path)
        if audio is None:
            return None

        try:
            timestamps = model.get_speech_timestamps(
                audio,
                threshold=self._threshold,
                min_silence_duration_ms=self._min_silence_duration_ms,
                return_seconds=True,
            )
            logger.info("[VAD] 检测到 %d 个语音片段", len(timestamps))
            return timestamps
        except AttributeError:
            try:
                import silero_vad

                timestamps = silero_vad.get_speech_timestamps(
                    audio,
                    model,
                    threshold=self._threshold,
                    min_silence_duration_ms=self._min_silence_duration_ms,
                    return_seconds=True,
                )
                logger.info("[VAD] 检测到 %d 个语音片段 (alt API)", len(timestamps))
                return timestamps
            except Exception as e2:
                logger.warning("[VAD] 语音检测失败 (alt): %s", e2)
                return None
        except Exception as e:
            logger.error("[VAD] 语音检测失败: %s", e, exc_info=True)
            return None

    def trim_trailing_silence(self, audio_path: str) -> str:
        """去除音频末尾的静音段。

        如果 VAD 不可用或无语音，返回原始路径。

        Args:
            audio_path: 原始音频文件路径

        Returns:
            修剪后的音频文件路径（可能和原始路径相同）
        """
        timestamps = self.detect_speech(audio_path)
        if not timestamps:
            return audio_path

        last_end = timestamps[-1]["end"]
        trim_end_ms = int(last_end * 1000) + 500

        try:
            import pydub

            audio = pydub.AudioSegment.from_file(audio_path)
            trim_end_ms = min(trim_end_ms, len(audio))
            trimmed = audio[:trim_end_ms]

            suffix = Path(audio_path).suffix or ".wav"
            with NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = tmp.name
            trimmed.export(tmp_path, format=Path(tmp_path).suffix.lstrip("."))
            logger.info(
                "[VAD] 音频修剪: %dms → %dms (语音结束于 %.2fs)",
                len(audio),
                len(trimmed),
                last_end,
            )
            return tmp_path
        except Exception as e:
            logger.warning("[VAD] 修剪失败: %s，返回原始音频", e)
            return audio_path


class ASRManager:
    """语音识别管理器（服务端 FunASR，Web Speech 降级在浏览器端实现）。"""

    def __init__(self) -> None:
        self.provider: str = settings.asr_provider
        self.model_name: str = "paraformer-zh"
        self._model = None  # lazy load
        self.vad = VADManager()

    def _load_model(self) -> Any | None:
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

    async def _run_sync(self, func, *args, **kwargs):
        """在线程池中运行同步函数，带 30 秒超时防护。

        Args:
            func: 同步函数
            *args: 传递给 func 的位置参数
            **kwargs: 传递给 func 的关键字参数

        Returns:
            func 的返回值，超时或异常时抛出
        """
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args, **kwargs),
            timeout=30.0,
        )

    async def transcribe(self, audio_path: str) -> str | None:
        """使用 FunASR 转写音频文件。

        流程：VAD 修剪尾部静音 → FunASR 识别。
        VAD 不可用时直接走 FunASR。
        所有同步阻塞操作通过 _run_sync 迁移到线程池，释放事件循环。

        Args:
            audio_path: 音频文件路径

        Returns:
            识别文本或 None
        """
        try:
            model = await self._run_sync(self._load_model)
        except asyncio.TimeoutError:
            logger.error("[ASR] 模型加载超时")
            return None
        if model is None:
            logger.warning("[ASR] FunASR 不可用，返回 None")
            return None

        # VAD 修剪静音尾部（通过线程池避免阻塞事件循环）
        try:
            trimmed_path = await self._run_sync(self.vad.trim_trailing_silence, audio_path)
        except asyncio.TimeoutError:
            logger.warning("[ASR] VAD 修剪超时，使用原始音频")
            trimmed_path = audio_path
        is_trimmed = trimmed_path != audio_path

        try:
            result = await self._run_sync(model.generate, input=trimmed_path)
            text = result[0].get("text", "") if result else ""
            if text:
                logger.info("[ASR] 识别成功: %s", text[:50])
                return text
            logger.warning("[ASR] 识别结果为空")
            return None
        except asyncio.TimeoutError:
            logger.error("[ASR] ASR 识别超时")
            return None
        except Exception as e:
            logger.error("[ASR] ASR 识别失败: %s", e, exc_info=True)
            return None
        finally:
            if is_trimmed:
                Path(trimmed_path).unlink(missing_ok=True)

    def unload_model(self) -> None:
        """卸载 ASR 模型释放内存。"""
        self._model = None
        logger.info("[ASR] 模型已卸载")


asr_manager = ASRManager()
vad_manager = asr_manager.vad
