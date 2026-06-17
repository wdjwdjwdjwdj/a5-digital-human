"""对话编排：LLM + RAG + 上下文管理。"""

from backend.config import settings


class ChatBot:
    """对话引擎，负责编排 LLM 与 RAG 检索。"""

    def __init__(self) -> None:
        self.llm_provider = settings.llm_provider
        self.model = settings.deepseek_model

    async def chat(self, query: str, context: str | None = None) -> str | None:
        """生成回答。

        Args:
            query: 用户输入
            context: 可选的 RAG 检索上下文

        Returns:
            回答文本或 None
        """
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
            messages = []
            if context:
                messages.append({"role": "system", "content": context})
            messages.append({"role": "user", "content": query})

            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[ChatBot] LLM 调用失败: {e}")
            return None


chatbot = ChatBot()
