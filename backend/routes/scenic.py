"""对话路由：文字/语音输入 → LLM → TTS 完整链路。"""

import logging
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

from backend.services.chatbot import chatbot
from backend.services.tts_service import tts_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["对话"])


class MessageRequest(BaseModel):
    """文字对话请求体。"""

    query: str = Field(..., description="用户输入文本")


class StreamRequest(BaseModel):
    """流式对话请求体。"""

    query: str = Field(..., description="用户输入文本")


# 景区知识库上下文（待 P3a Dify RAG 就绪后替换为实时检索）
_SCENIC_CONTEXT = (
    "你是杭州西湖景区的智能导游，名叫'小西'。"
    "请用热情、专业的语气回答游客关于西湖的问题。"
    "提供景点介绍、历史文化、游览路线、美食推荐等信息。"
)


@router.post("/message")
async def send_message(req: MessageRequest) -> dict:
    """文字对话：发送消息 → LLM 回答。

    Args:
        req: 包含 query 字段的 JSON 请求体

    Returns:
        {"reply": str, "audio": bool}
    """
    logger.info("[Chat] 收到文字消息: %s", req.query[:50])
    reply = await chatbot.chat(req.query, context=_SCENIC_CONTEXT)
    if reply:
        logger.info("[Chat] 回答: %s", reply[:80])
        return {"reply": reply, "audio": False}
    logger.warning("[Chat] 回答为空")
    return {"reply": "抱歉，我现在无法回答，请稍后再试。", "audio": False}


@router.post("/voice")
async def voice_chat(
    audio: UploadFile = File(...),
    text: str = Form(default=""),
) -> dict:
    """语音对话：音频 → ASR(可选) → LLM → TTS → 返回音频。

    Args:
        audio: 用户录音文件 (WAV/WebM)
        text: 前端 ASR 识别的文本（如果前端已做 ASR）

    Returns:
        {"reply": str, "audio_url": str | None, "asr_text": str}
    """
    query = text

    # 如果前端没有做 ASR，保存音频供服务端 ASR
    if not query:
        try:
            from backend.services.asr_service import asr_manager

            ext = Path(audio.filename or "audio.wav").suffix or ".wav"
            with NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp_path = tmp.name
                content = await audio.read()
                tmp.write(content)
            query = asr_manager.transcribe(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)
            if not query:
                return {"reply": "抱歉，我没有听清您说什么。", "audio_url": None, "asr_text": ""}
        except Exception as e:
            logger.error("[Chat] ASR 处理失败: %s", e, exc_info=True)
            return {"reply": "语音识别出错，请用文字输入。", "audio_url": None, "asr_text": ""}

    logger.info("[Chat] 语音识别结果: %s", query[:50])

    # LLM 回答
    reply = await chatbot.chat(query, context=_SCENIC_CONTEXT)
    if not reply:
        return {"reply": "抱歉，我现在无法回答。", "audio_url": None, "asr_text": query}

    # TTS 合成
    audio_data = await tts_manager.synthesize(reply)
    audio_url = None
    if audio_data:
        audio_dir = Path("data/audio")
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_filename = f"{uuid.uuid4().hex}.wav"
        audio_path = audio_dir / audio_filename
        audio_path.write_bytes(audio_data)
        audio_url = f"/static/audio/{audio_filename}"
        logger.info("[Chat] TTS 音频已保存: %s", audio_path)

    return {"reply": reply, "audio_url": audio_url, "asr_text": query}


@router.post("/stream")
async def stream_message(req: StreamRequest) -> dict:
    """流式对话接口（轮询模式，用于前端打字机效果）。"""
    reply = await chatbot.chat(req.query, context=_SCENIC_CONTEXT)
    return {"reply": reply or "抱歉，我现在无法回答。"}
