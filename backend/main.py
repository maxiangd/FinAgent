"""FinAgent Lab 后端数据服务：AKShare 行情/K线 接口。

运行：uvicorn main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.docs import setup_docs
from app.exception_handlers import register_exception_handlers
from app.routers.agent_data_preview import router as agent_data_preview_router
from app.routers.agent_tasks import router as agent_tasks_router
from app.routers.health import router as health_router
from app.routers.market import router as market_router
from app.routers.paper import router as paper_router
from app.routers.providers import router as providers_router

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("finagent.startup")


def _warm_caches() -> None:
    """后台预热代码表（首次约 8 秒），避免用户第一次查询时等待。"""
    try:
        from data_sources.market.stock_name_service import warm_code_table

        warm_code_table()
        logger.info("代码表预热完成")
    except Exception:  # noqa: BLE001
        logger.warning("代码表预热失败", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_warm_caches, name="cache-warmup", daemon=True).start()
    yield


app = FastAPI(
    title="FinAgent Lab 数据服务",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,  # 自定义 /docs，Swagger UI 资源走国内镜像
    redoc_url=None,
)
register_exception_handlers(app)
setup_docs(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(market_router)
app.include_router(agent_tasks_router)
app.include_router(agent_data_preview_router)
app.include_router(providers_router)
app.include_router(paper_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
