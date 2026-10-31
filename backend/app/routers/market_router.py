"""股票搜索、K 线和行情快照路由。"""

import asyncio
import logging
from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from services.market.kline_data_service import get_kline
from services.market.market_snapshot_service import get_snapshot
from services.market.stock_name_service import search_stock

logger = logging.getLogger("finagent.market.routes")
router = APIRouter(prefix="/api", tags=["market"])


@router.get("/search")
async def search(q: str, limit: int = 8):
    """按代码或名称搜索股票，返回候选列表。"""
    try:
        return await asyncio.to_thread(search_stock, q, limit)
    except Exception as e:  # noqa: BLE001
        logger.exception("search 失败 %s", q)
        raise HTTPException(status_code=502, detail=f"搜索失败: {e}") from e


@router.get("/stock/{code}/kline")
async def kline(
    code: str,
    period: Literal["daily", "weekly", "monthly"] = "daily",
    limit: Optional[int] = None,
    start_date: date | None = None,
    end_date: date | None = None,
    warmup_bars: int = Query(default=0, ge=0, le=200),
):
    """获取股票 K 线；可限定日期范围，并额外请求指标计算用的预热 K 线。"""
    try:
        return await asyncio.to_thread(
            get_kline,
            code,
            limit,
            period,
            start_date,
            end_date,
            warmup_bars,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("kline 失败 %s", code)
        raise HTTPException(status_code=502, detail=f"数据源错误: {e}") from e


@router.get("/stock/{code}/snapshot")
async def snapshot(code: str):
    """获取股票行情与基本面快照。"""
    try:
        return await asyncio.to_thread(get_snapshot, code)
    except Exception as e:  # noqa: BLE001
        logger.exception("snapshot 失败 %s", code)
        raise HTTPException(status_code=502, detail=f"数据源错误: {e}") from e
