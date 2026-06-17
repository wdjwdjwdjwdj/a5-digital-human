"""健康检查路由。"""

from fastapi import APIRouter

router = APIRouter(tags=["健康检查"])


@router.get("/ping")
async def ping() -> dict:
    """服务存活检查。"""
    return {"pong": True}
