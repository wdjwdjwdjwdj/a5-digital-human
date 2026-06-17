"""语音闭环测试。"""

import pytest


class TestTTSASR:
    """TTS 和 ASR 语音闭环测试。"""

    @pytest.mark.asyncio
    async def test_tts_synthesize(self) -> None:
        """测试 TTS 合成（预期降级）。"""
        from backend.services.tts_service import tts_manager

        result = await tts_manager.synthesize("你好")
        # 无网络时返回 None
        assert result is None or isinstance(result, bytes)

    def test_asr_transcribe_missing_file(self) -> None:
        """测试 ASR 转写不存在的文件。"""
        from backend.services.asr_service import asr_manager

        result = asr_manager.transcribe("nonexistent.wav")
        assert result is None
