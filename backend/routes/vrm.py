"""VRM 3D 模型切换路由（无状态设计）。"""

import logging
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vrm", tags=["VRM"])

_MODEL_BASE = Path("frontend/static/vrm")


class ModelSwitchRequest(BaseModel):
    """模型切换请求体。"""

    path: str = Field(..., description="VRM 模型文件名（如 AliciaSolid.vrm）")


class ModelSwitchResponse(BaseModel):
    """模型切换响应体。"""

    success: bool
    model_path: str
    message: str


@router.post("/model", response_model=ModelSwitchResponse)
async def switch_model(req: ModelSwitchRequest) -> ModelSwitchResponse:
    """切换 VRM 3D 模型。

    无状态设计：前端传入模型文件名，后端只验证文件存在性并返回。
    前端拿到结果后自行热加载新模型。

    Args:
        req: 包含模型文件名的请求体

    Returns:
        切换结果（success + 模型路径 + 消息）
    """
    # 路径遍历防护：规范化路径后检查是否在允许目录内
    model_path = (_MODEL_BASE / req.path).resolve()
    if not str(model_path).startswith(str(_MODEL_BASE.resolve())):
        logger.warning("[VRM] 路径遍历攻击拦截: %s", req.path)
        return ModelSwitchResponse(
            success=False,
            model_path=req.path,
            message="非法的模型路径",
        )

    if not model_path.is_file():
        logger.warning("[VRM] 模型文件不存在: %s", model_path)
        return ModelSwitchResponse(
            success=False,
            model_path=req.path,
            message=f"模型文件不存在: {req.path}",
        )

    # 检查是否为 .vrm 文件
    if model_path.suffix.lower() != ".vrm":
        logger.warning("[VRM] 非 VRM 文件: %s", model_path)
        return ModelSwitchResponse(
            success=False,
            model_path=req.path,
            message=f"文件格式不支持（仅支持 .vrm）: {req.path}",
        )

    logger.info("[VRM] 模型切换请求成功: %s", req.path)
    return ModelSwitchResponse(
        success=True,
        model_path=req.path,
        message=f"模型已切换为 {req.path}，请等待前端热加载",
    )


@router.get("/models", response_model=list[dict[str, str]])
async def list_models() -> list[dict[str, str]]:
    """列出所有可用的 VRM 模型文件。

    Returns:
        模型文件列表，每项包含 name 和 path
    """
    if not _MODEL_BASE.exists():
        return []

    models: list[dict[str, str]] = []
    for item in sorted(_MODEL_BASE.iterdir()):
        if item.is_file() and item.suffix.lower() == ".vrm":
            models.append({"name": item.stem, "path": str(item.relative_to(_MODEL_BASE))})
    return models
