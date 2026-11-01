"""股票搜索、K 线和行情快照路由。"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from data_sources.market.kline_data_service import get_kline
from data_sources.market.market_snapshot_service import get_snapshot
from data_sources.market.stock_name_service import search_stock

router = APIRouter(prefix="/api", tags=["market"])


@router.get("/search")
async def search(q: str, limit: int = 8):
    """按代码或名称搜索股票，返回候选列表。"""
    return await asyncio.to_thread(search_stock, q, limit)


@router.get("/stock/{code}/kline")
async def kline(
    code: str,
    period: Literal["daily", "weekly", "monthly"] = "daily",
    limit: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    warmup_bars: int = Query(default=0, ge=0, le=200),
):
    """获取股票 K 线；可限定日期范围，并额外请求指标计算用的预热 K 线。"""
    return await asyncio.to_thread(
        get_kline, code, limit, period, start_date, end_date, warmup_bars
    )


@router.get("/stock/{code}/snapshot")
async def snapshot(code: str):
    """获取股票行情与基本面快照。"""
    return await asyncio.to_thread(get_snapshot, code)
