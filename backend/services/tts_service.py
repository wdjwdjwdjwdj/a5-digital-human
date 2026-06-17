"""Edge-TTS 及降级 TTS 服务封装。"""

from edge_tts import Communicate


class TTSManager:
    """语音合成管理器，支持降级方案。"""

    def __init__(self) -> None:
        self.provider: str = "edge-tts"
        self.voice: str = "zh-CN-XiaoxiaoNeural"

    async def synthesize(self, text: str) -> bytes | None:
        """合成语音。

        Args:
            text: 要合成的文本

        Returns:
            ｜音频字节流，None 表示失败
        """
        try:
            communicate = Communicate(text, self.voice)
            audio = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio += chunk["data"]
            return audio
        except Exception as e:
            print(f"[TTS] Edge-TTS 合成失败: {e}")
            return None

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
            engine.save_to_file(text, "tts_fallback.wav")
            engine.runAndWait()
            with open("tts_fallback.wav", "rb") as f:
                return f.read()
        except Exception as e:
            print(f"[TTS] pyttsx3 降级也失败: {e}")
            return None


tts_manager = TTSManager()
