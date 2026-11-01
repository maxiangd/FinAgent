"""分析任务的创建、状态查询、事件订阅与取消。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agents.llm_provider_client import LLMConfigurationError, UnknownProviderError
from app.schemas.analysis_schemas import (
    AnalysisTaskRequest,
    AnalysisTaskResponse,
    AnalysisTaskSummary,
    TaskStatus,
)
from app.task_manager import FINISHED_STATUSES, TaskRecord, task_manager

router = APIRouter(prefix="/api/analysis/tasks", tags=["analysis-tasks"])


def _to_response(record: TaskRecord) -> AnalysisTaskResponse:
    return AnalysisTaskResponse(
        task_id=record.task_id,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        request=record.request,
        error=record.error,
        result=record.result,
    )


def _get_or_404(task_id: str) -> TaskRecord:
    record = task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"任务不存在：{task_id}")
    return record


@router.post("", response_model=AnalysisTaskResponse, status_code=202)
async def create_task(request: AnalysisTaskRequest):
    """创建分析任务并在后台执行，立即返回任务 ID。"""
    try:
        record = task_manager.create_task(request)
    except UnknownProviderError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LLMConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _to_response(record)


@router.get("", response_model=list[AnalysisTaskSummary])
async def list_tasks(limit: int = 20):
    """最近的分析任务，包含服务重启前的历史任务。"""
    summaries = []
    for document in task_manager.list_tasks(limit):
        request = document.get("request") or {}
        created_at = document.get("created_at")
        if created_at is None:
            continue
        summaries.append(
            AnalysisTaskSummary(
                task_id=document["task_id"],
                status=TaskStatus(document.get("status", TaskStatus.FAILED.value)),
                stock_code=str(request.get("stock_code") or ""),
                period=request.get("period"),
                created_at=created_at,
                updated_at=document.get("updated_at") or created_at,
            )
        )
    return summaries


@router.get("/{task_id}", response_model=AnalysisTaskResponse)
async def get_task(task_id: str):
    """查询任务状态与最终结果。"""
    return _to_response(_get_or_404(task_id))


@router.post("/{task_id}/cancel", response_model=AnalysisTaskResponse)
async def cancel_task(task_id: str):
    """请求取消运行中的任务；已结束的任务不会被取消。"""
    record = _get_or_404(task_id)
    task_manager.cancel_task(task_id)
    return _to_response(record)


@router.get("/{task_id}/events")
async def stream_events(task_id: str, request: Request):
    """通过 SSE 推送任务事件；任务结束后自动关闭。"""
    record = _get_or_404(task_id)

    async def event_stream():
        sent = 0
        last_event_id = request.headers.get("last-event-id", "")
        events = record.snapshot_events()
        if last_event_id:
            # 断线重连时不重复推送已经收到的事件
            for index, event in enumerate(events):
                if event.event_id == last_event_id:
                    sent = index + 1
                    break
        idle_ticks = 0
        while True:
            events = record.snapshot_events()
            while sent < len(events):
                event = events[sent]
                yield f"id: {event.event_id}\ndata: {event.model_dump_json()}\n\n"
                sent += 1
                idle_ticks = 0
            if record.status in FINISHED_STATUSES and sent >= len(events):
                break
            idle_ticks += 1
            if idle_ticks % 20 == 0:  # 约每 10 秒发一次保活注释
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
