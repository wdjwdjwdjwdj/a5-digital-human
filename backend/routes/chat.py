"""对话路由。"""

from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["对话"])


@router.post("/message")
async def send_message(query: str) -> dict:
    """发送对话消息。"""
    return {"query": query, "reply": "待实现"}
