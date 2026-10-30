"""FinAgent Lab 后端数据服务：AKShare 行情/K线 接口。

运行：uvicorn main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.health import router as health_router
from routers.market import router as market_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="FinAgent Lab 数据服务", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(market_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
