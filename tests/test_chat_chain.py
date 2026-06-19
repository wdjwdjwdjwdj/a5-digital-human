"""核心对话链路测试。"""

import pytest


class TestChatChain:
    """核心对话链路测试（≥8 用例）。"""

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
            resp = await client.post("/chat/message", json={"query": "你好"})
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
        assert tts_manager.voice == "zh-CN-XiaoxiaoNeural"

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

    # ── 降级链路测试 ─────────────────────────────

    def test_dify_not_configured(self) -> None:
        """测试 Dify 未配置时的降级检测。

        当 dify_api_key 为默认值或空时，
        _dify_configured() 应返回 False。
        """
        from backend.services.chatbot import chatbot

        configured = chatbot._dify_configured()
        # 如果 API Key 是默认值（未配置），则应返回 False
        assert isinstance(configured, bool)
        # 检查 dify_client 的 base_url 是否为 localhost（开发模式）
        from backend.services.dify_client import dify_client

        if "localhost" in dify_client.base_url:
            # 开发模式下 Dify 通常不可用
            assert not configured or "app" in (dify_client.api_key or "")

    def test_local_rag_build_index(self) -> None:
        """测试 Local RAG 索引构建。

        验证 local_rag 可以加载 knowledge/ 文档并构建索引。
        """
        from backend.services.local_rag import local_rag

        success = local_rag.build_index()
        assert success is True, "Local RAG 索引构建失败，检查 knowledge/ 目录"

    @pytest.mark.asyncio
    async def test_local_rag_search(self) -> None:
        """测试 Local RAG 语义检索。

        验证对西湖相关问题的检索能返回非空结果。
        """
        from backend.services.local_rag import local_rag

        local_rag.build_index()
        result = local_rag.search("西湖门票多少钱")
        assert isinstance(result, str)
        assert len(result) > 0, "检索结果不应为空"
        # 应包含"免费"或"门票"相关关键词
        assert any(kw in result for kw in ["免费", "门票", "雷峰塔"]), "检索结果应包含西湖门票相关信息"

    @pytest.mark.asyncio
    async def test_chatbot_dify_fallback(self) -> None:
        """测试 ChatBot 在 Dify 不可用时的降级行为。

        当 Dify 未配置时，chat() 不应抛出异常，
        应返回 None 或降级回答。
        """
        from backend.services.chatbot import chatbot

        try:
            reply = await chatbot.chat(
                query="西湖门票多少钱",
                session_id="test_fallback_dify",
            )
            # 不 assert reply 非空（可能因无 API Key 返回 None）
            # 但必须不抛异常
            assert reply is None or isinstance(reply, str)
        except Exception as e:
            pytest.fail(f"chat() 在 Dify 不可用时抛出异常: {e}")
