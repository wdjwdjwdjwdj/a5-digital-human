"""对话路由：文字/语音输入 → LLM → TTS 完整链路 + SSE 流式 TTS。"""

import base64
import json
import logging
import re
import time
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.repository.chat_repo import chat_repo
from backend.services.chatbot import chatbot
from backend.services.tts_service import tts_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["对话"])

# 景区知识库上下文（Dify 不可用时的降级上下文）
_SCENIC_CONTEXT = (
    "你是杭州西湖景区智能导游'小西'。热情专业口语化，介绍景点/历史/路线/美食。"
    "回答 ≤ 100 字。末尾附 [情绪: happy/sad/angry/surprise/neutral]。"
)

_EMOTION_RE = re.compile(r"\[情绪:\s*\w+\]")


def _strip_emotion_tag(text: str) -> tuple[str, str | None]:
    """剥离回答末尾的情绪标签，返回 (纯净文本, 情绪) 二元组。

    Args:
        text: 可能包含 [情绪: xxx] 标签的原始回答

    Returns:
        (去标签后的文本, 情绪词或 None)
    """
    match = _EMOTION_RE.search(text)
    if match:
        emotion = match.group().replace("[情绪:", "").replace("]", "").strip()
        clean = text.replace(match.group(), "").strip()
        return clean, emotion
    return text, None


def _cleanup_old_audio(audio_dir: Path, max_files: int = 200, max_age_minutes: int = 60) -> None:
    """清理旧的音频文件，保留最近 max_files 个文件，删除超过 max_age_minutes 的旧文件。

    Args:
        audio_dir: 音频文件目录
        max_files: 保留的最大文件数
        max_age_minutes: 文件最大存活时间（分钟）
    """
    if not audio_dir.exists():
        return
    try:
        now = time.time()
        cutoff = now - max_age_minutes * 60
        files = sorted(audio_dir.glob("*.wav"), key=lambda f: f.stat().st_mtime, reverse=True)
        for i, f in enumerate(files):
            if i >= max_files or f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("[Chat] 清理旧音频失败: %s", e)


def _save_audio(audio_data: bytes | None) -> str | None:
    """将音频数据保存到 static/audio 目录并返回可访问的 URL。

    Args:
        audio_data: 原始 WAV 音频字节数据

    Returns:
        可访问的音频 URL 字符串，保存失败或 audio_data 为空时返回 None
    """
    if not audio_data:
        return None
    try:
        static_audio_dir = Path(__file__).parent.parent / "frontend" / "static" / "audio"
        static_audio_dir.mkdir(parents=True, exist_ok=True)
        audio_filename = f"{uuid.uuid4().hex}.wav"
        audio_path = static_audio_dir / audio_filename
        audio_path.write_bytes(audio_data)
        _cleanup_old_audio(static_audio_dir)
        logger.info("[Chat] TTS 音频已保存: %s", audio_path)
        return f"/static/audio/{audio_filename}"
    except Exception as e:
        logger.error("[Chat] 保存音频失败: %s", e, exc_info=True)
        return None


class MessageRequest(BaseModel):
    """文字对话请求体。"""

    query: str = Field(..., min_length=1, max_length=2000, description="用户输入文本")
    session_id: str = Field(default="default", max_length=64, description="会话 ID，用于多轮对话")


class StreamRequest(BaseModel):
    """流式对话请求体。"""

    query: str = Field(..., min_length=1, max_length=2000, description="用户输入文本")
    session_id: str = Field(default="default", max_length=64, description="会话 ID")


@router.post("/message")
async def send_message(req: MessageRequest) -> dict:
    """文字对话：发送消息 → LLM 回答 + TTS 音频。

    Args:
        req: 包含 query 和 session_id 的 JSON 请求体

    Returns:
        {"reply": str, "audio_url": str | None, "emotion": str | None}
    """
    logger.info("[Chat] 收到文字消息: %s (session=%s)", req.query[:50], req.session_id[:8])
    reply = await chatbot.chat(req.query, context=_SCENIC_CONTEXT, session_id=req.session_id)
    if not reply:
        logger.warning("[Chat] 回答为空")
        return {"reply": "抱歉，我现在无法回答，请稍后再试。", "audio_url": None, "emotion": None}

    # 剥离情绪标签，TTS 用纯净文本
    clean_reply, emotion = _strip_emotion_tag(reply)

    chat_repo.save_conversation(req.query, reply, provider="deepseek", session_id=req.session_id)

    # TTS 合成完整音频（一次性合成，避免分片间隙）
    audio_url = _save_audio(await tts_manager.synthesize(clean_reply))

    logger.info("[Chat] 回答: %s", reply[:80])
    return {"reply": reply, "audio_url": audio_url, "emotion": emotion}


@router.post("/voice")
async def voice_chat(
    audio: UploadFile = File(),  # noqa: B008
    text: str = Form(default=""),
    session_id: str = Form(default="default"),
) -> dict:
    """语音对话：音频 → ASR(可选) → LLM → TTS → 返回音频。

    Args:
        audio: 用户录音文件 (WAV/WebM)
        text: 前端 ASR 识别的文本（如果前端已做 ASR）
        session_id: 会话 ID，用于多轮对话

    Returns:
        {"reply": str, "audio_url": str | None, "asr_text": str}
    """
    # 文件大小限制（10MB）
    if audio and audio.size and audio.size > 10 * 1024 * 1024:
        return {"reply": "音频文件过大，请录制 10MB 以内的语音。", "audio_url": None, "asr_text": ""}

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
            query = await asr_manager.transcribe(tmp_path)
            Path(tmp_path).unlink(missing_ok=True)
            if not query:
                return {"reply": "抱歉，我没有听清您说什么。", "audio_url": None, "asr_text": ""}
        except Exception as e:
            logger.error("[Chat] ASR 处理失败: %s", e, exc_info=True)
            return {"reply": "语音识别出错，请用文字输入。", "audio_url": None, "asr_text": ""}

    logger.info("[Chat] 语音识别结果: %s (session=%s)", query[:50], session_id[:8])

    # LLM 回答
    reply = await chatbot.chat(query, context=_SCENIC_CONTEXT, session_id=session_id)
    if not reply:
        return {"reply": "抱歉，我现在无法回答。", "audio_url": None, "asr_text": query}

    # 剥离情绪标签
    clean_reply, emotion = _strip_emotion_tag(reply)

    # 持久化对话记录
    chat_repo.save_conversation(query, reply, provider="deepseek", session_id=session_id)

    # TTS 合成（用纯净文本）
    audio_url = _save_audio(await tts_manager.synthesize(clean_reply))

    return {"reply": reply, "audio_url": audio_url, "asr_text": query, "emotion": emotion}


@router.post("/stream")
async def stream_message(req: StreamRequest) -> dict:
    """文字对话接口（普通 JSON 响应，用于前端打字机效果的轮询模式）。

    注意：此接口返回完整的 JSON 响应（非 SSE 流式），
    前端打字机效果是客户端侧模拟实现。真正的服务端流式请使用 /chat/stream-tts 。

    Args:
        req: 包含 query 和 session_id 的请求体

    Returns:
        {"reply": str}
    """
    reply = await chatbot.chat(req.query, context=_SCENIC_CONTEXT, session_id=req.session_id)
    if reply:
        chat_repo.save_conversation(req.query, reply, provider="deepseek", session_id=req.session_id)
    return {"reply": reply or "抱歉，我现在无法回答。"}


@router.get("/stream-tts")
async def stream_tts(text: str):
    """SSE 流式 TTS 端点。

    将文本合成语音后按 chunk 流式返回，前端可边接收边播放。
    首包延迟 < 1.5 秒（Edge-TTS 模式下）。

    Args:
        text: 要合成的文本（URL 编码）

    Returns:
        text/event-stream 响应
        data: {"type": "audio", "data": "base64chunk..."}
        data: {"type": "done"}
    """

    async def event_generator():
        try:
            async for audio_chunk in tts_manager.stream_synthesize(text):
                if not audio_chunk:
                    continue
                audio_b64 = base64.b64encode(audio_chunk).decode("utf-8")
                yield f"data: {json.dumps({'type': 'audio', 'data': audio_b64})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error("[SSE] TTS 流式失败: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'data': 'TTS 流式合成失败'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
