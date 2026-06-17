"""核心对话链路测试。"""

import pytest


class TestChatChain:
    """核心对话链路测试（≥5 用例）。"""

    @pytest.mark.asyncio
    async def test_health_check(self) -> None:
        """测试健康检查接口。"""
        from httpx import ASGITransport, AsyncClient

        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_chat_message(self) -> None:
        """测试对话消息接口。"""
        from httpx import ASGITransport, AsyncClient

        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/chat/message", params={"query": "你好"})
        assert resp.status_code == 200

    def test_dify_client_init(self) -> None:
        """测试 Dify 客户端初始化。"""
        from backend.services.dify_client import dify_client

        assert dify_client is not None
        assert "localhost" in dify_client.base_url

    def test_tts_manager_init(self) -> None:
        """测试 TTS 管理器初始化。"""
        from backend.services.tts_service import tts_manager

        assert tts_manager is not None
        assert tts_manager.provider == "edge-tts"

    def test_asr_manager_init(self) -> None:
        """测试 ASR 管理器初始化。"""
        from backend.services.asr_service import asr_manager

        assert asr_manager is not None
        assert asr_manager.provider == "funasr"

    def test_settings_load(self) -> None:
        """测试配置加载。"""
        from backend.config import settings

        assert settings.llm_provider == "deepseek"
        assert settings.env == "development"
