"""景区导览 AI 数字人主入口。"""

import asyncio
import logging
import sys
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.routes.chat import router as chat_router
from backend.routes.health import router as health_router
from backend.routes.scenic import router as scenic_router
from backend.routes.vrm import router as vrm_router

# ── 日志配置 ──────────────────────────────────────────────

# ── 速率限制（内存滑动窗口） ──────────────────────────────
_CHAT_RATE_LIMIT: int = 60  # 每分钟最多 60 次请求
_CHAT_RATE_WINDOW: float = 60.0  # 滑动窗口大小（秒）


class _RateLimiter:
    """简单内存速率限制器，基于滑动窗口计数器。

    按客户端 IP 和请求路径前缀分别计数。
    窗口大小和限制可通过类属性调整。
    """

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)

    async def check(self, request: Request) -> bool:
        """检查请求是否超过速率限制。

        Args:
            request: FastAPI 请求对象

        Returns:
            True 表示允许通过，False 表示超过限制
        """
        # 仅对 /chat/ 开头的路径做速率限制
        if not request.url.path.startswith("/chat/"):
            return True

        client_ip: str = request.client.host if request.client else "unknown"
        key = f"{client_ip}:chat"
        now = time.time()
        window = self._windows[key]

        # 移除窗口外的旧时间戳
        cutoff = now - _CHAT_RATE_WINDOW
        while window and window[0] < cutoff:
            window.pop(0)

        if len(window) >= _CHAT_RATE_LIMIT:
            logger.warning("[RateLimit] 超出限制: IP=%s, 当前窗口=%d 次", client_ip, len(window))
            return False

        window.append(now)
        return True


_rate_limiter = _RateLimiter()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("main")


# ── 生命周期 ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动与关闭时的初始化/清理工作。"""
    # startup
    Path("data").mkdir(exist_ok=True)
    static_audio = STATIC_DIR / "audio"
    static_audio.mkdir(parents=True, exist_ok=True)
    if not settings.deepseek_api_key:
        logger.warning("DEEPSEEK_API_KEY 未配置，LLM 功能不可用")
    else:
        logger.info("DeepSeek API Key 已配置")
    if not settings.admin_password:
        logger.warning("ADMIN_PASSWORD 未配置，管理后台登录不受保护！请设置 ADMIN_PASSWORD 环境变量")

    # FunASR 模型预热（后台异步加载，不阻塞启动流程）
    try:
        from backend.services.asr_service import asr_manager

        await asyncio.to_thread(asr_manager._load_model)
        logger.info("[预热] FunASR 模型加载完成")
    except Exception:
        logger.warning("[预热] FunASR 模型加载失败，将在首次使用时按需加载")

    logger.info("服务启动完成，环境: %s", settings.env)
    yield
    # shutdown (如有需要在此添加清理逻辑)


# ── FastAPI 应用 ─────────────────────────────────────────
app = FastAPI(
    title="A5-景区导览AI数字人",
    description="第十五届中国软件杯 A5 赛题 - 基于 Open-LLM-VTuber",
    version="0.1.0",
    lifespan=lifespan,
)

# ── 安全响应头中间件（必须在 app 创建后面） ─────────────
_SELF = "'self'"
_CSP = (
    f"default-src {_SELF}; "
    f"script-src {_SELF} 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    f"style-src {_SELF} 'unsafe-inline' https://fonts.googleapis.com; "
    f"img-src {_SELF} data: https:; "
    f"font-src {_SELF} https://fonts.gstatic.com; "
    f"connect-src {_SELF} ws://localhost:* http://localhost:*; "
    f"frame-src 'none'; object-src 'none'; base-uri {_SELF}"
)
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(self), microphone=(self), geolocation=()",
    "Content-Security-Policy": _CSP,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cache-Control": "no-cache, no-store, must-revalidate",
}


@app.middleware("http")
async def add_security_headers(request, call_next):
    """为所有响应添加安全响应头。"""
    response: Response = await call_next(request)
    for key, value in _SECURITY_HEADERS.items():
        response.headers[key] = value
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """速率限制中间件（仅对 /chat/ 端点生效）。"""
    allowed = await _rate_limiter.check(request)
    if not allowed:
        logger.warning("[RateLimit] 请求被拒绝: %s %s", request.method, request.url.path)
        return Response(
            content='{"reply": "请求过于频繁，请稍后再试。", "audio_url": null, "emotion": null}',
            media_type="application/json",
            status_code=429,
            headers={"Retry-After": "60"},
        )
    return await call_next(request)


# ── CORS ─────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.env == "development" else [settings.cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 静态文件 ─────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "frontend" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── 注册路由 ─────────────────────────────────────────────
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(vrm_router)
app.include_router(scenic_router)


@app.get("/")
async def root():
    """返回前端页面。"""
    index = Path(__file__).parent / "frontend" / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return {"message": "A5 景区导览AI数字人服务运行中，请部署前端页面。"}


@app.get("/dashboard")
async def dashboard_page():
    """返回数据大屏页面。"""
    dashboard = Path(__file__).parent / "frontend" / "dashboard.html"
    if dashboard.exists():
        return FileResponse(str(dashboard))
    return {"message": "dashboard.html 未找到，请确保前端文件已部署。"}


@app.get("/admin")
async def admin_page():
    """返回管理后台页面。"""
    admin = Path(__file__).parent / "frontend" / "admin.html"
    if admin.exists():
        return FileResponse(str(admin))
    return {"message": "admin.html 未找到，请确保前端文件已部署。"}
