"""健康检查路由 + Token 消耗统计。"""

import logging

from fastapi import APIRouter

from backend.config import settings
from backend.services.chatbot import chatbot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["健康检查"])


@router.get("/health")
async def health() -> dict:
    """服务健康状态检查。"""
    return {"status": "ok", "env": settings.env}


@router.get("/ping")
async def ping() -> dict:
    """服务存活检查。"""
    return {"pong": True}


@router.get("/token-stats")
async def token_stats() -> dict:
    """Token 消耗统计（用于监控 API 费用）。"""
    try:
        stats = chatbot.get_token_stats()
        return {"status": "ok", **stats}
    except Exception as e:
        logger.error("[Health] Token 统计失败: %s", e, exc_info=True)
        return {"status": "error", "detail": "获取 Token 统计失败"}
