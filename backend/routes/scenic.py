"""景区 REST API 路由层：11 个端点，覆盖景区信息、景点、活动、路线 CRUD。"""

import logging
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from backend.config import settings
from backend.repository.scenic_repo import ScenicRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scenic", tags=["景区"])

# ── 解析数据库路径 ─────────────────────────────────────────
_db_url: str = settings.database_url
_db_path: str = _db_url.replace("sqlite:///", "")
if not _db_path:
    _db_path = "data/conversations.db"
Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

_repo = ScenicRepository(_db_path)


def _check_admin_token(request: Request) -> None:
    """校验管理后台鉴权 token。

    Args:
        request: FastAPI 请求对象

    Raises:
        HTTPException: token 无效或缺失时返回 401
    """
    token = request.headers.get("X-Admin-Token", "")
    if not token or token != settings.admin_password:
        raise HTTPException(status_code=401, detail="Unauthorized: 无效的管理员令牌")


def _response(success: bool, data: any = None, error: str | None = None) -> dict:
    """构建统一 JSON 响应格式。"""
    return {"success": success, "data": data, "error": error}


async def _ensure_db() -> None:
    """确保数据库表已初始化，种子数据已填充。"""
    try:
        await _repo.init_db()
        await _repo.init_seed_data()
    except Exception:
        logger.error("[ScenicRoute] 数据库初始化失败: %s", traceback.format_exc())


# ── GET 端点 ──────────────────────────────────────────────


@router.get("/area")
async def get_scenic_area() -> dict:
    """获取景区基础信息。"""
    try:
        await _ensure_db()
        area = await _repo.get_area_info()
        return _response(True, area)
    except Exception as e:
        logger.error("[ScenicRoute] GET /area 失败: %s", traceback.format_exc())
        return _response(False, error=str(e))


@router.get("/spots")
async def get_spots(category: str | None = None) -> dict:
    """获取景点列表，支持按 category 过滤。"""
    try:
        await _ensure_db()
        spots = await _repo.get_spots(category)
        return _response(True, spots)
    except Exception as e:
        logger.error("[ScenicRoute] GET /spots 失败: %s", traceback.format_exc())
        return _response(False, error=str(e))


@router.get("/spots/{spot_id}")
async def get_spot(spot_id: str) -> dict:
    """获取单个景点详情。"""
    try:
        await _ensure_db()
        spot = await _repo.get_spot_by_spot_id(spot_id)
        if not spot:
            return _response(False, error=f"景点 {spot_id} 未找到")
        return _response(True, spot)
    except Exception as e:
        logger.error("[ScenicRoute] GET /spots/%s 失败: %s", spot_id, traceback.format_exc())
        return _response(False, error=str(e))


@router.get("/activities")
async def get_activities() -> dict:
    """获取活动列表。"""
    try:
        await _ensure_db()
        activities = await _repo.get_activities()
        return _response(True, activities)
    except Exception as e:
        logger.error("[ScenicRoute] GET /activities 失败: %s", traceback.format_exc())
        return _response(False, error=str(e))


@router.get("/routes")
async def get_routes() -> dict:
    """获取路线列表（每条路线含关联景点列表）。"""
    try:
        await _ensure_db()
        routes = await _repo.get_routes()
        return _response(True, routes)
    except Exception as e:
        logger.error("[ScenicRoute] GET /routes 失败: %s", traceback.format_exc())
        return _response(False, error=str(e))


@router.get("/routes/{route_id}")
async def get_route(route_id: int) -> dict:
    """获取单个路线详情（含关联景点）。"""
    try:
        await _ensure_db()
        route = await _repo.get_route_by_id(route_id)
        if not route:
            return _response(False, error=f"路线 {route_id} 未找到")
        return _response(True, route)
    except Exception as e:
        logger.error("[ScenicRoute] GET /routes/%d 失败: %s", route_id, traceback.format_exc())
        return _response(False, error=str(e))


@router.get("/stats")
async def get_stats() -> dict:
    """获取景区统计信息。"""
    try:
        await _ensure_db()
        stats = await _repo.get_stats()
        return _response(True, stats)
    except Exception as e:
        logger.error("[ScenicRoute] GET /stats 失败: %s", traceback.format_exc())
        return _response(False, error=str(e))


# ── 配置管理 ─────────────────────────────────────────────

_CONFIG_DEFAULTS: dict[str, str] = {
    "scenic_name": "灵山胜境",
    "guide_name": "灵灵",
    "ai_persona": (
        "你是无锡灵山胜境智能导游'灵灵'。热情专业口语化，"
        "介绍佛教文化/景点/历史/路线/美食。"
        "回答≤100字。末尾附[情绪:happy/sad/angry/surprise/neutral]。"
    ),
    "default_tts_voice": "zh-CN-XiaoxiaoNeural",
}


@router.get("/config")
async def get_config() -> dict:
    """获取景区配置（含景区名称、导游名称、AI人设、TTS音色）。"""
    try:
        config = await _repo.get_config()
        return _response(True, config)
    except Exception:
        logger.error("[ScenicRoute] GET /config 失败: %s", traceback.format_exc())
        return _response(True, dict(_CONFIG_DEFAULTS))


@router.put("/config")
async def update_config(data: dict) -> dict:
    """更新景区配置。

    请求体：{"scenic_name": "...", "guide_name": "...", ...}
    只更新提供的字段，未提供的保留原值。
    """
    try:
        current = await _repo.get_config()
        merged = dict(current)
        for key in _CONFIG_DEFAULTS:
            if key in data and data[key] is not None:
                merged[key] = str(data[key])
        result = await _repo.save_config(merged)
        logger.info(
            "[ScenicRoute] 配置已更新: scenic_name=%s, guide_name=%s",
            merged.get("scenic_name"), merged.get("guide_name"),
        )
        return _response(True, result)
    except Exception as e:
        logger.error("[ScenicRoute] PUT /config 失败: %s", traceback.format_exc())
        return _response(False, error=str(e))


@router.get("/ai-responses")
async def get_ai_responses() -> dict:
    """获取 AI 常见问答配置。"""
    try:
        await _ensure_db()
        responses = await _repo.get_ai_responses()
        return _response(True, responses)
    except Exception as e:
        logger.error("[ScenicRoute] GET /ai-responses 失败: %s", traceback.format_exc())
        return _response(False, error=str(e))


# ── POST/PUT/DELETE（需鉴权） ─────────────────────────────


@router.post("/spots")
async def create_spot(request: Request, data: dict) -> dict:
    """新增景点（需 X-Admin-Token 鉴权）。"""
    _check_admin_token(request)
    try:
        await _ensure_db()
        required = ("name", "category")
        for field in required:
            if field not in data:
                raise HTTPException(status_code=400, detail=f"缺少必填字段: {field}")
        spot = await _repo.create_spot(data)
        if not spot:
            return _response(False, error="新增景点失败")
        return _response(True, spot)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[ScenicRoute] POST /spots 失败: %s", traceback.format_exc())
        return _response(False, error=str(e))


@router.put("/spots/{spot_id}")
async def update_spot(spot_id: str, request: Request, data: dict) -> dict:
    """更新景点信息（需 X-Admin-Token 鉴权）。"""
    _check_admin_token(request)
    try:
        await _ensure_db()
        updated = await _repo.update_spot(spot_id, data)
        if not updated:
            return _response(False, error=f"景点 {spot_id} 未找到")
        return _response(True, updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[ScenicRoute] PUT /spots/%s 失败: %s", spot_id, traceback.format_exc())
        return _response(False, error=str(e))


@router.delete("/spots/{spot_id}")
async def delete_spot(spot_id: str, request: Request) -> dict:
    """删除景点（需 X-Admin-Token 鉴权）。"""
    _check_admin_token(request)
    try:
        await _ensure_db()
        deleted = await _repo.delete_spot(spot_id)
        if not deleted:
            return _response(False, error=f"景点 {spot_id} 未找到")
        return _response(True, {"deleted": True})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[ScenicRoute] DELETE /spots/%s 失败: %s", spot_id, traceback.format_exc())
        return _response(False, error=str(e))
