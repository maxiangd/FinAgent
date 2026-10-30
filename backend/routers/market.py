"""股票搜索、K 线和行情快照路由。"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from services import market as market_service

logger = logging.getLogger("finagent.market.routes")
router = APIRouter(prefix="/api", tags=["market"])


@router.get("/search")
async def search(q: str, limit: int = 8):
    """按代码或名称搜索股票，返回候选列表。"""
    try:
        return await asyncio.to_thread(market_service.search_stock, q, limit)
    except Exception as e:  # noqa: BLE001
        logger.exception("search 失败 %s", q)
        raise HTTPException(status_code=502, detail=f"搜索失败: {e}") from e


@router.get("/stock/{code}/kline")
async def kline(code: str, limit: int = 520):
    """获取股票 K 线数据。"""
    try:
        return await asyncio.to_thread(market_service.get_kline, code, limit)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("kline 失败 %s", code)
        raise HTTPException(status_code=502, detail=f"数据源错误: {e}") from e


@router.get("/stock/{code}/snapshot")
async def snapshot(code: str):
    """获取股票行情与基本面快照。"""
    try:
        return await asyncio.to_thread(market_service.get_snapshot, code)
    except Exception as e:  # noqa: BLE001
        logger.exception("snapshot 失败 %s", code)
        raise HTTPException(status_code=502, detail=f"数据源错误: {e}") from e
