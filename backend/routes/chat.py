"""对话路由：文字/语音输入 → LLM → TTS 完整链路 + SSE 流式 TTS。"""

import asyncio
import base64
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from backend.repository.chat_repo import _EMOTION_SATISFACTION_MAP, chat_repo
from backend.services.chatbot import chatbot
from backend.services.tts_service import tts_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["对话"])

# 景区知识库上下文（Dify 不可用时的降级上下文）
_SCENIC_CONTEXT = (
    "你是无锡灵山胜境的AI导游灵灵，你非常了解灵山胜境的文化、历史、宗教和旅游信息。"
    "灵山胜境位于太湖之滨，是国家AAAAA级旅游景区。"
    "核心景点包括灵山大佛（88米青铜大佛）、九龙灌浴、灵山梵宫等。"
    "景区开放时间8:00-17:00，门票210元。"
    "热情专业口语化。回答 ≤ 100 字。末尾附 [情绪: happy/sad/angry/surprise/neutral]。"
)

_EMOTION_RE = re.compile(r"\[情绪:\s*\w+\]")

# 音频文件类型白名单（MIME 类型）
_ALLOWED_AUDIO_TYPES: frozenset[str] = frozenset(
    {
        "audio/wav",
        "audio/x-wav",
        "audio/webm",
        "audio/mpeg",
        "audio/mp3",
        "audio/ogg",
        "audio/x-m4a",
    }
)


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

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        """去除首尾空白字符，防止空白绕过 min_length 检查。"""
        return v.strip()

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        """校验 session_id 字段，只允许安全字符集。"""
        v = v.strip()
        if not re.match(r"^[\w\-.]{1,64}$", v):
            raise ValueError("session_id 只能包含字母、数字、下划线、短横线和点号")
        return v


class StreamRequest(BaseModel):
    """流式对话请求体。"""

    query: str = Field(..., min_length=1, max_length=2000, description="用户输入文本")
    session_id: str = Field(default="default", max_length=64, description="会话 ID")

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        """去除首尾空白字符，防止空白绕过 min_length 检查。"""
        return v.strip()

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        """校验 session_id 字段，只允许安全字符集。"""
        v = v.strip()
        if not re.match(r"^[\w\-.]{1,64}$", v):
            raise ValueError("session_id 只能包含字母、数字、下划线、短横线和点号")
        return v


class MultimodalRequest(BaseModel):
    """多模态图片对话请求体。"""

    query: str = Field(..., min_length=1, max_length=2000, description="用户输入文本")
    image_base64: str = Field(..., min_length=1, max_length=8 * 1024 * 1024, description="图片的 base64 编码")
    session_id: str = Field(default="default", max_length=64, description="会话 ID")

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        """去除首尾空白字符，防止空白绕过 min_length 检查。"""
        return v.strip()

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        """校验 session_id 字段，只允许安全字符集。"""
        v = v.strip()
        if not re.match(r"^[\w\-.]{1,64}$", v):
            raise ValueError("session_id 只能包含字母、数字、下划线、短横线和点号")
        return v

    @field_validator("image_base64")
    @classmethod
    def validate_base64(cls, v: str) -> str:
        """校验 base64 字符串格式，防止注入非 base64 内容。"""
        # base64 仅允许 A-Za-z0-9+/= 字符
        if not re.match(r"^[A-Za-z0-9+/]*={0,2}$", v):
            raise ValueError("非法的 base64 编码格式")
        return v


@router.post("/multimodal")
async def multimodal_chat(req: MultimodalRequest) -> dict:
    """多模态图片对话：图片 + 文字 → VL 模型识别 → TTS 播报。

    接收用户上传的景区照片（base64）和文字问题，
    调用通义千问VL 多模态模型识别图片并生成回答。

    Args:
        req: 包含 query / image_base64 / session_id 的请求体

    Returns:
        {"reply": str, "audio_url": str | None, "emotion": str | None}
    """
    # ── 后端校验图片大小（≤ 4MB 二进制）─────────────
    try:
        if len(req.image_base64) > 6 * 1024 * 1024:
            return {"reply": "图片数据过大，请压缩后重新上传。", "audio_url": None, "emotion": None}
        image_data = base64.b64decode(req.image_base64)
        if len(image_data) > 4 * 1024 * 1024:
            logger.warning("[Chat] 多模态图片过大: %d bytes", len(image_data))
            return {"reply": "图片大小不能超过 4MB，请压缩后重新上传。", "audio_url": None, "emotion": None}
        # 魔数校验确保是有效图片格式
        _VALID_IMAGE_HEADERS = (b"\xff\xd8\xff", b"\x89PNG", b"RIFF", b"GIF8", b"\x00\x00\x00\x0c", b"\x00\x00\x00\x1c")
        if not any(image_data.startswith(h) for h in _VALID_IMAGE_HEADERS):
            logger.warning("[Chat] 无效图片魔数: %s", image_data[:8].hex())
            return {"reply": "不支持的图片格式，请上传 JPG/PNG/WebP 图片。", "audio_url": None, "emotion": None}
    except Exception as e:
        logger.warning("[Chat] 多模态图片 base64 解码失败: %s", e)
        return {"reply": "图片格式不正确，请上传有效的图片文件。", "audio_url": None, "emotion": None}

    logger.info(
        "[Chat] 多模态消息: %s (session=%s, image=%d bytes)",
        req.query[:50],
        req.session_id[:8],
        len(image_data),
    )

    reply = await chatbot.chat_with_image(req.query, req.image_base64, req.session_id)
    if not reply:
        reply = "抱歉，我现在无法回答。"

    # 剥离情绪标签，TTS 用纯净文本
    clean_reply, emotion = _strip_emotion_tag(reply)

    # 持久化对话记录
    await chat_repo.save_conversation(req.query, reply, provider="qwen-vl", session_id=req.session_id)

    # TTS 合成音频
    audio_url = _save_audio(await tts_manager.synthesize(clean_reply))

    logger.info("[Chat] 多模态回答: %s", reply[:80])
    return {"reply": reply, "audio_url": audio_url, "emotion": emotion}


@router.post("/message")
async def send_message(req: MessageRequest) -> dict:
    """文字对话：发送消息 → LLM 回答 + TTS 音频。

    Args:
        req: 包含 query 和 session_id 的 JSON 请求体

    Returns:
        {"reply": str, "audio_url": str | None, "emotion": str | None}
    """
    logger.info("[Chat] 收到文字消息: %s (session=%s)", req.query[:50], req.session_id[:8])
    try:
        reply = await chatbot.chat(req.query, context=_SCENIC_CONTEXT, session_id=req.session_id)
    except Exception as e:
        logger.error("[Chat] LLM 调用失败: %s", e, exc_info=True)
        return {"reply": "抱歉，服务异常，请稍后再试。", "audio_url": None, "emotion": None}
    if not reply:
        logger.warning("[Chat] 回答为空")
        return {"reply": "抱歉，我现在无法回答，请稍后再试。", "audio_url": None, "emotion": None}

    # 剥离情绪标签，TTS 用纯净文本
    clean_reply, emotion = _strip_emotion_tag(reply)
    # 情感标签 → 满意度数值
    sat = _EMOTION_SATISFACTION_MAP.get(emotion) if emotion else None

    await chat_repo.save_conversation(
        req.query,
        reply,
        provider="deepseek",
        session_id=req.session_id,
        satisfaction=sat,
    )

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
    # 会话 ID 长度校验：截断过长的 session_id 防止注入和 DOS
    if len(session_id) > 64:
        logger.warning("[Chat] 截断过长 session_id: %d chars", len(session_id))
        session_id = session_id[:64]

    # 文件大小限制（10MB）
    if audio and audio.size and audio.size > 10 * 1024 * 1024:
        return {"reply": "音频文件过大，请录制 10MB 以内的语音。", "audio_url": None, "asr_text": ""}

    # 音频文件 MIME 类型白名单校验
    if audio and audio.content_type and audio.content_type not in _ALLOWED_AUDIO_TYPES:
        logger.warning("[Chat] 不支持的音频 MIME 类型: %s", audio.content_type)
        return {"reply": "不支持的音频格式，请使用 WAV/WebM/MP3/OGG 格式。", "audio_url": None, "asr_text": ""}

    query = text

    # 如果前端没有做 ASR，保存音频供服务端 ASR
    if not query:
        try:
            from backend.services.asr_service import asr_manager

            content = await audio.read()
            # 读取后二次校验文件大小（audio.size 可能为 None，此处确保不超过 10MB）
            if len(content) > 10 * 1024 * 1024:
                logger.warning("[Chat] 语音文件过大: %d bytes", len(content))
                return {"reply": "音频文件过大，请录制 10MB 以内的语音。", "audio_url": None, "asr_text": ""}

            ext = Path(audio.filename or "audio.wav").suffix or ".wav"
            with NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp_path = tmp.name
                await asyncio.to_thread(tmp.write, content)
            query = await asr_manager.transcribe(tmp_path)
            await asyncio.to_thread(Path(tmp_path).unlink, missing_ok=True)
            if not query:
                return {"reply": "抱歉，我没有听清您说什么。", "audio_url": None, "asr_text": ""}
        except Exception as e:
            logger.error("[Chat] ASR 处理失败: %s", e, exc_info=True)
            return {"reply": "语音识别出错，请用文字输入。", "audio_url": None, "asr_text": ""}

    logger.info("[Chat] 语音识别结果: %s (session=%s)", query[:50], session_id[:8])

    # LLM 回答
    try:
        reply = await chatbot.chat(query, context=_SCENIC_CONTEXT, session_id=session_id)
    except Exception as e:
        logger.error("[Chat] 语音 LLM 调用失败: %s", e, exc_info=True)
        return {"reply": "抱歉，服务异常，请稍后再试。", "audio_url": None, "asr_text": query if query else ""}
    if not reply:
        return {"reply": "抱歉，我现在无法回答。", "audio_url": None, "asr_text": query}

    # 剥离情绪标签
    clean_reply, emotion = _strip_emotion_tag(reply)
    sat = _EMOTION_SATISFACTION_MAP.get(emotion) if emotion else None

    # 持久化对话记录
    await chat_repo.save_conversation(query, reply, provider="deepseek", session_id=session_id, satisfaction=sat)

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
    try:
        reply = await chatbot.chat(req.query, context=_SCENIC_CONTEXT, session_id=req.session_id)
    except Exception as e:
        logger.error("[Chat] Stream LLM 调用失败: %s", e, exc_info=True)
        return {"reply": "抱歉，服务异常，请稍后再试。"}
    if reply:
        _, emotion = _strip_emotion_tag(reply)
        sat = _EMOTION_SATISFACTION_MAP.get(emotion) if emotion else None
        await chat_repo.save_conversation(
            req.query,
            reply,
            provider="deepseek",
            session_id=req.session_id,
            satisfaction=sat,
        )
    return {"reply": reply or "抱歉，我现在无法回答。"}


@router.get("/stream-tts")
async def stream_tts(query: str = "", text: str = "", session_id: str = "default"):
    """SSE 流式端点：LLM 流式 → 累积成句 → TTS 流式管道。

    两种模式：
    1. query 模式（新）：接收用户问题 → LLM streaming → 逐句 TTS streaming
    2. text 模式（旧）：接收已有文本 → TTS streaming（向后兼容）

    query 模式首包延迟优化：不等 LLM 完整回答，逐句推入 TTS。

    Args:
        query: 用户问题（新模式）
        text: 已有文本（旧模式，向后兼容）
        session_id: 会话 ID

    Returns:
        text/event-stream 响应
        data: {"type": "sentence", "data": "text"}
        data: {"type": "audio", "data": "base64chunk..."}
        data: {"type": "done"}
    """
    # ── 输入校验 ────────────────────────────────────────
    effective_query = query.strip() if query else ""
    effective_text = text.strip() if text else ""

    if not effective_query and not effective_text:

        async def _empty_error() -> AsyncGenerator[str, None]:
            yield f"data: {json.dumps({'type': 'error', 'data': 'query 或 text 参数不能为空'})}\n\n"

        return StreamingResponse(
            _empty_error(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    if len(effective_query) > 2000 or len(effective_text) > 2000:
        logger.warning("[SSE] 参数过长: query=%d text=%d", len(effective_query), len(effective_text))

        async def _len_error() -> AsyncGenerator[str, None]:
            yield f"data: {json.dumps({'type': 'error', 'data': '内容过长（最大 2000 字符）'})}\n\n"

        return StreamingResponse(
            _len_error(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    if len(session_id) > 64:
        logger.warning("[SSE] 截断过长 session_id: %d chars", len(session_id))
        session_id = session_id[:64]

    # ── 句子切分配置 ────────────────────────────────────
    _SENTENCE_PATTERN = re.compile(r"[。！？\n]")
    _MIN_SENTENCE_LEN = 10

    # ── 旧模式：纯 TTS 流式（向后兼容） ─────────────────
    if effective_text and not effective_query:

        async def _tts_only_generator() -> AsyncGenerator[str, None]:
            try:
                async for audio_chunk in tts_manager.stream_synthesize(effective_text):
                    if not audio_chunk:
                        continue
                    audio_b64 = base64.b64encode(audio_chunk).decode("utf-8")
                    yield f"data: {json.dumps({'type': 'audio', 'data': audio_b64})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                logger.error("[SSE] 旧模式 TTS 流式失败: %s", e, exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'data': 'TTS 流式合成失败'})}\n\n"

        return StreamingResponse(
            _tts_only_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # ── 新模式：LLM streaming → 累积成句 → TTS streaming ──

    async def _tts_for_sentence(sentence: str) -> AsyncGenerator[bytes, None]:
        """单句 TTS 流式合成，失败时回退到完整合成。

        Args:
            sentence: 要合成的句子（可能含情绪标签）

        Yields:
            音频字节片段
        """
        # 剥离情绪标签
        clean = _EMOTION_RE.sub("", sentence).strip()
        if not clean:
            return

        try:
            async for chunk in tts_manager.stream_synthesize(clean):
                if chunk:
                    yield chunk
            return
        except Exception as e:
            logger.warning("[SSE] 句子 TTS 流式失败，回退完整合成: %s", e)

        # 回退：完整合成一次性返回
        audio = await tts_manager.synthesize(clean)
        if audio:
            yield audio

    async def _llm_tts_generator() -> AsyncGenerator[str, None]:
        """LLM streaming → 累积成句 → TTS streaming 主逻辑。"""
        sentence_buffer = ""
        start_time = time.monotonic()
        max_duration = 30.0

        try:
            # ── 启动 LLM 流式 ──────────────────────────────
            token_stream = chatbot.chat_stream(
                effective_query,
                context=_SCENIC_CONTEXT,
                session_id=session_id,
            )

            # 第一 token 超时检测
            first_token = None
            try:
                first_token = await asyncio.wait_for(
                    token_stream.__anext__(),
                    timeout=5.0,
                )
            except StopAsyncIteration:
                # 空响应，直接结束
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            except asyncio.TimeoutError:
                logger.warning("[SSE] 首 token 等待超时 (5s)")
                await token_stream.aclose()
                yield f"data: {json.dumps({'type': 'error', 'data': 'AI 响应超时，请稍后重试'})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            sentence_buffer += first_token

            # ── 处理后续 token ─────────────────────────────
            async for token in token_stream:
                elapsed = time.monotonic() - start_time
                if elapsed > max_duration:
                    logger.warning("[SSE] 流式总时长超时 (%.1fs)", elapsed)
                    await token_stream.aclose()
                    # 处理已有 buffer 中的剩余内容
                    remaining = sentence_buffer.strip()
                    if remaining:
                        async for audio_chunk in _tts_for_sentence(remaining):
                            audio_b64 = base64.b64encode(audio_chunk).decode("utf-8")
                            yield f"data: {json.dumps({'type': 'audio', 'data': audio_b64})}\n\n"
                    break

                sentence_buffer += token

                # 尝试切分句子
                scan_pos = 0
                while scan_pos < len(sentence_buffer):
                    match = _SENTENCE_PATTERN.search(sentence_buffer, scan_pos)
                    if not match:
                        break
                    end_idx = match.end()
                    candidate = sentence_buffer[:end_idx].strip()
                    if len(candidate) >= _MIN_SENTENCE_LEN:
                        # 找到一个可拆分的句子
                        sentence = candidate
                        sentence_buffer = sentence_buffer[end_idx:]
                        scan_pos = 0

                        # 发送句子文本 SSE
                        yield f"data: {json.dumps({'type': 'sentence', 'data': sentence})}\n\n"

                        # TTS 流式合成该句子
                        async for audio_chunk in _tts_for_sentence(sentence):
                            audio_b64 = base64.b64encode(audio_chunk).decode("utf-8")
                            yield f"data: {json.dumps({'type': 'audio', 'data': audio_b64})}\n\n"
                    else:
                        scan_pos = end_idx

            # ── 处理剩余 buffer ────────────────────────────
            remaining = sentence_buffer.strip()
            if remaining:
                yield f"data: {json.dumps({'type': 'sentence', 'data': remaining})}\n\n"
                async for audio_chunk in _tts_for_sentence(remaining):
                    audio_b64 = base64.b64encode(audio_chunk).decode("utf-8")
                    yield f"data: {json.dumps({'type': 'audio', 'data': audio_b64})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            logger.error("[SSE] LLM→TTS 流式失败: %s", e, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'data': '流式处理失败'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        _llm_tts_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
