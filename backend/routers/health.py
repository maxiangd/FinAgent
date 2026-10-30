"""服务健康检查路由。"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    """确认后端服务已启动。"""
    return {"status": "ok", "service": "finagent-data"}
