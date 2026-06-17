"""健康检查路由。"""

from fastapi import APIRouter

from backend.config import settings

router = APIRouter(tags=["健康检查"])


@router.get("/health")
async def health() -> dict:
    """服务健康状态检查。"""
    return {"status": "ok", "env": settings.env}


@router.get("/ping")
async def ping() -> dict:
    """服务存活检查。"""
    return {"pong": True}
