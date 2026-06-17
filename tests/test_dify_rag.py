"""Dify RAG 检索测试。"""

import pytest


class TestDifyRAG:
    """RAG 知识库检索测试。"""

    @pytest.mark.asyncio
    async def test_dify_client_chat(self) -> None:
        """测试 Dify 对话请求（无实际 API 密钥时降级）。"""
        from backend.services.dify_client import dify_client

        result = await dify_client.chat("西湖门票多少钱")
        # 预期：因无实际 API 密钥，返回 None
        assert result is None

    def test_knowledge_docs_exist(self) -> None:
        """测试知识库文档存在。"""
        from pathlib import Path
        knowledge_dir = Path("knowledge")
        assert knowledge_dir.exists()
        md_files = list(knowledge_dir.glob("*.md"))
        assert len(md_files) >= 5
