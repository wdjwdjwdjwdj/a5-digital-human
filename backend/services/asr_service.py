"""FunASR 语音识别封装，支持降级方案。"""


class ASRManager:
    """语音识别管理器，支持 Web Speech API 降级。"""

    def __init__(self) -> None:
        self.provider: str = "funasr"

    def transcribe(self, audio_path: str) -> str | None:
        """使用 FunASR 转写音频文件。

        Args:
            audio_path: 音频文件路径

        Returns:
            识别文本或 None
        """
        try:
            from funasr import AutoModel

            model = AutoModel(
                model="paraformer-zh",
                device="cpu",
            )
            result = model.generate(input=audio_path)
            return result[0]["text"] if result else None
        except Exception as e:
            print(f"[ASR] FunASR 识别失败: {e}")
            return None


asr_manager = ASRManager()
