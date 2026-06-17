"""景区导览 AI 数字人主入口。"""

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings

# ── 日志配置 ──────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("main")

# ── FastAPI 应用 ─────────────────────────────────────────
app = FastAPI(
    title="A5-景区导览AI数字人",
    description="第十五届中国软件杯 A5 赛题 - 基于 Open-LLM-VTuber",
    version="0.1.0",
)

# ── CORS ─────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段开放；生产环境限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 静态文件 ─────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "frontend" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── 注册路由 ─────────────────────────────────────────────
from backend.routes.health import router as health_router
from backend.routes.chat import router as chat_router

app.include_router(health_router)
app.include_router(chat_router)


@app.get("/")
async def root():
    """返回前端页面。"""
    from fastapi.responses import FileResponse

    index = Path(__file__).parent / "frontend" / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "A5 景区导览AI数字人服务运行中，请部署前端页面。"}


@app.on_event("startup")
async def startup():
    """应用启动时的初始化工作。"""
    # 确保目录存在
    Path("data").mkdir(exist_ok=True)
    static_audio = STATIC_DIR / "audio"
    static_audio.mkdir(parents=True, exist_ok=True)
    # 检查 API Key
    if not settings.deepseek_api_key:
        logger.warning("DEEPSEEK_API_KEY 未配置，LLM 功能不可用")
    else:
        logger.info("DeepSeek API Key 已配置")
    logger.info("服务启动完成，监听端口: %s", settings.env)
