"""景区导览 AI 数字人主入口。"""

from fastapi import FastAPI
from backend.config import settings

app = FastAPI(
    title="A5-景区导览AI数字人",
    description="第十五届中国软件杯 A5 赛题 - 基于 Open-LLM-VTuber",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict:
    """健康检查接口。"""
    return {"status": "ok", "env": settings.env}
