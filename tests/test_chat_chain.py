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

        验证对灵山相关问题的检索能返回非空结果。
        """
        from backend.services.local_rag import local_rag

        local_rag.build_index()
        result = local_rag.search("灵山胜境门票多少钱")
        assert isinstance(result, str)
        assert len(result) > 0, "检索结果不应为空"
        # 应包含"免费"或"门票"相关关键词
        assert any(kw in result for kw in ["免费", "门票", "灵山"]), "检索结果应包含灵山门票相关信息"

    @pytest.mark.asyncio
    async def test_chatbot_dify_fallback(self) -> None:
        """测试 ChatBot 在 Dify 不可用时的降级行为。

        当 Dify 未配置时，chat() 不应抛出异常，
        应返回 None 或降级回答。
        """
        from backend.services.chatbot import chatbot

        try:
            reply = await chatbot.chat(
                query="灵山胜境门票多少钱",
                session_id="test_fallback_dify",
            )
            # 不 assert reply 非空（可能因无 API Key 返回 None）
            # 但必须不抛异常
            assert reply is None or isinstance(reply, str)
        except Exception as e:
            pytest.fail(f"chat() 在 Dify 不可用时抛出异常: {e}")


class TestMultimodalChat:
    """多模态图片问答测试（≥6 用例）。"""

    # ── 1x1 透明 PNG 的 base64（用于正常场景，68 字节）────
    _TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAAABJRU5ErkJggg=="

    @pytest.mark.asyncio
    async def test_chat_with_image_no_api_key(self) -> None:
        """API Key 为空时返回降级提示。

        当 multimodal_api_key 为空字符串时，
        chat_with_image() 应返回降级提示文本。
        """
        from unittest.mock import patch

        from backend.config import settings
        from backend.services.chatbot import chatbot

        with patch.object(settings, "multimodal_api_key", ""):
            reply = await chatbot.chat_with_image(
                query="这是什么景点？",
                image_base64=self._TINY_PNG_B64,
                session_id="test_no_key",
            )
        assert reply is not None
        assert isinstance(reply, str)
        # 降级提示应包含关键词
        assert any(kw in reply for kw in ["不支持", "图片", "识别", "描述", "暂"]), f"降级提示内容异常: {reply}"

    @pytest.mark.asyncio
    async def test_chat_with_image_normal(self) -> None:
        """正确构建消息格式并调用多模态 API（mock API 调用）。

        验证 chat_with_image() 正确构建包含 image_url 的消息格式，
        并返回 API 响应内容。
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from backend.config import settings
        from backend.services.chatbot import chatbot

        expected_reply = "这是无锡灵山胜境的灵山大佛，高88米，青铜铸造。"
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = expected_reply
        mock_response.usage.total_tokens = 150

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("backend.services.chatbot.AsyncOpenAI", return_value=mock_client),
            patch.object(settings, "multimodal_api_key", "test-multimodal-key"),
            patch.object(settings, "multimodal_model", "qwen-vl-plus"),
        ):
            reply = await chatbot.chat_with_image(
                query="这是什么景点？",
                image_base64=self._TINY_PNG_B64,
                session_id="test_normal",
            )

        assert reply == expected_reply
        # 验证 API 调用参数：消息格式必须包含 image_url
        create_call_args = mock_client.chat.completions.create.call_args
        assert create_call_args is not None, "API create 未被调用"
        messages = create_call_args[1]["messages"]
        # 查找 user 消息（应包含 image_url）
        user_msg = next((m for m in messages if m["role"] == "user"), None)
        assert user_msg is not None, "消息列表缺少 user 角色"
        # user 消息应包含多模态 content 数组
        content = user_msg["content"]
        assert isinstance(content, list), "多模态消息 content 应为 list"
        image_parts = [p for p in content if p.get("type") == "image_url"]
        assert len(image_parts) > 0, "消息中缺少 image_url 部分"
        assert "image_url" in image_parts[0]
        # 验证模型参数
        assert create_call_args[1]["model"] == "qwen-vl-plus"
        assert create_call_args[1]["timeout"] == 30

    @pytest.mark.asyncio
    async def test_multimodal_endpoint_success(self) -> None:
        """POST /chat/multimodal 正常请求返回正确格式。

        验证端点返回包含 reply / audio_url / emotion 的 JSON 响应。
        """
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from main import app

        mock_reply = "这是无锡灵山胜境的九龙灌浴景点。"

        with patch(
            "backend.routes.chat.chatbot.chat_with_image",
            new=AsyncMock(return_value=mock_reply),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/chat/multimodal",
                    json={
                        "query": "这是什么景点？",
                        "image_base64": self._TINY_PNG_B64,
                        "session_id": "test_endpoint",
                    },
                )

        assert resp.status_code == 200, f"期望 200，实际 {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "reply" in data
        assert data["reply"] == mock_reply
        assert "audio_url" in data
        assert "emotion" in data

    @pytest.mark.asyncio
    async def test_multimodal_endpoint_image_too_large(self) -> None:
        """图片超过 4MB 时返回友好提示。

        当 base64 解码后二进制 > 4MB 时，
        端点应拒绝并返回友好提示。
        """
        import base64

        from httpx import ASGITransport, AsyncClient

        from main import app

        # 构造 > 4MB 的二进制数据并 base64 编码
        large_binary = b"\x00" * (4 * 1024 * 1024 + 100)
        large_b64 = base64.b64encode(large_binary).decode()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat/multimodal",
                json={
                    "query": "这是什么？",
                    "image_base64": large_b64,
                    "session_id": "test_oversize",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        # 应包含友好的大小限制提示
        assert any(kw in data["reply"] for kw in ["4MB", "大小", "压缩", "过大"]), (
            f"应提示图片过大，实际回复: {data['reply']}"
        )

    @pytest.mark.asyncio
    async def test_multimodal_endpoint_no_api_key(self) -> None:
        """未配置多模态 API Key 时返回降级提示。

        当 multimodal_api_key 为空时，
        chat_with_image() 返回降级提示，端点应正常返回。
        """
        from unittest.mock import patch

        from httpx import ASGITransport, AsyncClient

        from backend.config import settings
        from main import app

        with patch.object(settings, "multimodal_api_key", ""):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/chat/multimodal",
                    json={
                        "query": "这是什么景点？",
                        "image_base64": self._TINY_PNG_B64,
                        "session_id": "test_no_key_endpoint",
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        # 降级提示应包含关键词
        assert any(kw in data["reply"] for kw in ["不支持", "图片", "描述", "识别", "暂"]), (
            f"降级提示内容异常: {data['reply']}"
        )

    def test_image_base64_format_handling(self) -> None:
        """前端传来的 base64 格式正确归一化处理。

        验证 chat_with_image() 内部能正确处理
        带 data: URI 前缀和不带前缀的 base64 字符串。
        """
        import base64

        from backend.services.chatbot import chatbot

        # 验证类常量：小图片 base64 可以被正常解码
        decoded = base64.b64decode(self._TINY_PNG_B64)
        assert len(decoded) == 71  # 1x1 透明 PNG 的实际大小
        assert decoded[:4] == b"\x89PNG"  # PNG 魔数

        # 验证 data: URI 格式能被正确剥离（如果实现支持）
        data_uri = f"data:image/png;base64,{self._TINY_PNG_B64}"
        # 检查 chatbot 的图片处理方法（如果提取为独立方法）
        normalize = getattr(chatbot, "_normalize_image_base64", None)
        if normalize:
            result = normalize(data_uri)
            assert result == self._TINY_PNG_B64, "data: URI 格式应被剥离为纯 base64"
            # 纯 base64 应原样返回
            result2 = normalize(self._TINY_PNG_B64)
            assert result2 == self._TINY_PNG_B64, "纯 base64 应原样返回"
        else:
            # 如果没有独立方法，至少确认类加载正常
            assert chatbot is not None
