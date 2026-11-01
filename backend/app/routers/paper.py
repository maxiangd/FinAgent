"""模拟交易接口：账户概览、建仓、平仓与重置（研究演示，不接入真实下单）。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.schemas.paper_schemas import PaperPortfolio, PaperPosition, PaperPositionCreate
from app.services.paper_service import paper_service

router = APIRouter(prefix="/api/paper", tags=["paper"])


@router.get("/portfolio", response_model=PaperPortfolio)
async def get_portfolio():
    """当前账户：现金、持仓市值、浮动与已实现盈亏。"""
    return await asyncio.to_thread(paper_service.get_portfolio)


@router.post("/positions", response_model=PaperPosition, status_code=201)
async def open_position(payload: PaperPositionCreate):
    """采纳某次已完成分析任务的 PM 结论，按最新价建仓。"""
    return await asyncio.to_thread(
        paper_service.open_position, payload.task_id, payload.quantity
    )


@router.post("/positions/{position_id}/close", response_model=PaperPosition)
async def close_position(position_id: str):
    """按最新价平仓，并把盈亏计入已实现收益。"""
    return await asyncio.to_thread(paper_service.close_position, position_id)


@router.post("/reset", response_model=PaperPortfolio)
async def reset_account():
    """清空持仓并恢复初始资金（演示用）。"""
    return await asyncio.to_thread(paper_service.reset)
