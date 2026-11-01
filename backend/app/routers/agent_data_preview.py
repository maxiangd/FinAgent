"""数据接入预览：只取数、不调用模型，用于确认本次分析能拿到哪些数据。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from agents.analysis_context_builder import build_initial_context
from app.presenters.analysis_response_builder import build_ingestion_response
from app.schemas.analysis_schemas import AnalysisTaskRequest, DataIngestionResponse

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/data-preview", response_model=DataIngestionResponse)
async def preview_analysis_data(request: AnalysisTaskRequest):
    """按股票、周期和区间取 K 线 / 基本面 / 新闻，返回带来源与限制说明的预览。"""
    state = await asyncio.to_thread(build_initial_context, request)
    return build_ingestion_response(request, state)
