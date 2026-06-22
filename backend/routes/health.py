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
    """Token 消耗统计（用于监控 API 费用）。

    开发环境返回完整统计信息，生产环境仅返回消耗总量以防止信息泄露。
    """
    try:
        stats = chatbot.get_token_stats()
        result = {"status": "ok"}
        if settings.env == "production":
            # 生产环境只暴露总量，隐藏内部细节（缓存命中率、压缩次数等）
            result["total_tokens"] = stats.get("total_tokens", 0)
        else:
            result.update(stats)
        return result
    except Exception as e:
        logger.error("[Health] Token 统计失败: %s", e, exc_info=True)
        return {"status": "error", "detail": "获取 Token 统计失败"}
