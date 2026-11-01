"""分析任务的生命周期管理：创建、后台执行、事件推送与取消。"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from agents.llm_provider_client import (
    LLMCallError,
    LLMConfigurationError,
    UnknownProviderError,
    load_llm_settings,
)
from agents.workflow import get_analysis_workflow, initial_workflow_state
from app.presenters.analysis_response_builder import (
    build_ingestion_response,
    build_run_response,
)
from app.schemas.analysis_schemas import (
    AnalysisError,
    AnalysisEvent,
    AnalysisEventType,
    AnalysisRunResponse,
    AnalysisStage,
    AnalysisTaskRequest,
    TaskStatus,
)
from app.services.task_repository import task_repository

logger = logging.getLogger("finagent.tasks")

FINISHED_STATUSES = (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)

# 节点 → 前端阶段
NODE_STAGE = {
    "load_context": AnalysisStage.INGEST,
    "market_analyst": AnalysisStage.ANALYST,
    "fundamental_analyst": AnalysisStage.ANALYST,
    "news_sentiment_analyst": AnalysisStage.ANALYST,
    "bull_researcher": AnalysisStage.DEBATE,
    "bear_researcher": AnalysisStage.DEBATE,
    "trader": AnalysisStage.TRADER,
    "aggressive_risk": AnalysisStage.RISK,
    "neutral_risk": AnalysisStage.RISK,
    "conservative_risk": AnalysisStage.RISK,
    "portfolio_manager": AnalysisStage.PM,
}

STAGE_LABEL = {
    AnalysisStage.INGEST: "数据接入",
    AnalysisStage.ANALYST: "分析师研报",
    AnalysisStage.DEBATE: "多空辩论",
    AnalysisStage.TRADER: "交易提案",
    AnalysisStage.RISK: "风控评审",
    AnalysisStage.PM: "PM 决策",
}


class _TaskCancelled(Exception):
    """任务被用户取消。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TaskRecord:
    """单个任务的运行时状态与事件流。"""

    task_id: str
    request: AnalysisTaskRequest
    status: TaskStatus = TaskStatus.QUEUED
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    events: list[AnalysisEvent] = field(default_factory=list)
    result: AnalysisRunResponse | None = None
    error: AnalysisError | None = None
    cancel_requested: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add_event(
        self,
        event_type: AnalysisEventType,
        stage: AnalysisStage | None = None,
        agent_name: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self.lock:
            self.events.append(
                AnalysisEvent(
                    task_id=self.task_id,
                    event_type=event_type,
                    stage=stage,
                    agent_name=agent_name,
                    message=message,
                    payload=payload or {},
                )
            )
            self.updated_at = _now()

    def set_status(self, status: TaskStatus, error: AnalysisError | None = None) -> None:
        with self.lock:
            self.status = status
            self.error = error
            self.updated_at = _now()

    def snapshot_events(self) -> list[AnalysisEvent]:
        with self.lock:
            return list(self.events)


def _error_code(exc: Exception) -> str:
    if isinstance(exc, UnknownProviderError):
        return "unknown_provider"
    if isinstance(exc, LLMConfigurationError):
        return "llm_not_configured"
    if isinstance(exc, LLMCallError):
        return "llm_call_failed"
    if isinstance(exc, LookupError):
        return "data_not_found"
    if isinstance(exc, ValueError):
        return "invalid_request"
    return "internal_error"


def _dump(model) -> dict | None:
    """把 pydantic 模型转成可 JSON 序列化的字典。"""
    return model.model_dump(mode="json") if model is not None else None


def _stage_payload(
    stage: AnalysisStage,
    request: AnalysisTaskRequest,
    state: dict[str, Any],
) -> dict[str, Any]:
    """阶段完成时把该阶段结果带进事件，前端可以立即渲染。"""
    evidence = list(state.get("evidence") or [])
    kline = state.get("kline_data") or {}

    if stage is AnalysisStage.INGEST:
        return {"ingestion": build_ingestion_response(request, state).model_dump(mode="json")}

    if stage is AnalysisStage.ANALYST:
        return {
            "analyst": {
                "report": _dump(state.get("market_report")),
                "stock_name": kline.get("name"),
                "stock_code": request.stock_code,
                "period": request.period,
                "actual_start_date": str(state.get("actual_start_date") or ""),
                "actual_end_date": str(state.get("actual_end_date") or ""),
                "model_name": state.get("market_model_name"),
                "limitations": list(dict.fromkeys(
                    limitation for item in evidence for limitation in item.limitations
                )),
                "evidence": [_dump(item) for item in evidence],
                "fundamental_report": _dump(state.get("fundamentals_report")),
                "news_report": _dump(state.get("news_report")),
            }
        }

    if stage is AnalysisStage.DEBATE:
        debate = state.get("investment_debate_state") or {}
        return {"debate_turns": [_dump(turn) for turn in (debate.get("history") or [])]}

    if stage is AnalysisStage.TRADER:
        return {"trade_proposal": _dump(state.get("trade_proposal"))}

    if stage is AnalysisStage.RISK:
        risk = state.get("risk_debate_state") or {}
        return {"risk_reviews": [_dump(review) for review in (risk.get("history") or [])]}

    if stage is AnalysisStage.PM:
        return {"pm_decision": _dump(state.get("pm_decision"))}

    return {}


def _record_document(record: TaskRecord) -> dict[str, Any]:
    """把任务转成可写入 MongoDB 的文档。"""
    return {
        "task_id": record.task_id,
        "status": record.status.value,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "request": record.request.model_dump(mode="json"),
        "error": record.error.model_dump(mode="json") if record.error else None,
        "result": record.result.model_dump(mode="json") if record.result else None,
        "events": [event.model_dump(mode="json") for event in record.snapshot_events()],
    }


def _record_from_document(document: dict[str, Any]) -> TaskRecord:
    """从 MongoDB 文档还原任务。"""
    record = TaskRecord(
        task_id=document["task_id"],
        request=AnalysisTaskRequest.model_validate(document["request"]),
        status=TaskStatus(document.get("status", TaskStatus.FAILED.value)),
        created_at=document.get("created_at") or _now(),
        updated_at=document.get("updated_at") or _now(),
    )
    if document.get("error"):
        record.error = AnalysisError.model_validate(document["error"])
    if document.get("result"):
        record.result = AnalysisRunResponse.model_validate(document["result"])
    record.events = [AnalysisEvent.model_validate(item) for item in document.get("events") or []]
    return record


class TaskManager:
    """进程内任务表；后续需要多 worker 时可替换为 Redis/MongoDB。"""

    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = threading.Lock()

    def create_task(self, request: AnalysisTaskRequest) -> TaskRecord:
        """校验配置后创建任务，并在后台线程执行。"""
        # 配置错误在创建阶段就返回，避免任务跑一半才失败
        load_llm_settings(request.provider)

        record = TaskRecord(task_id=uuid4().hex, request=request)
        with self._lock:
            self._tasks[record.task_id] = record
        record.add_event(AnalysisEventType.TASK_QUEUED, message="任务已创建，等待执行。")
        self._persist(record)
        threading.Thread(
            target=self._execute,
            args=(record,),
            name=f"analysis-{record.task_id[:8]}",
            daemon=True,
        ).start()
        return record

    def _persist(self, record: TaskRecord) -> None:
        task_repository.save(_record_document(record))

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            record = self._tasks.get(task_id)
        if record is not None:
            return record

        # 进程内没有时从 MongoDB 恢复；重启前仍在运行的任务标记为中断
        document = task_repository.get(task_id)
        if document is None:
            return None
        record = _record_from_document(document)
        if record.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
            record.set_status(
                TaskStatus.FAILED,
                error=AnalysisError(
                    code="interrupted",
                    message="服务重启导致任务中断，请重新发起分析。",
                ),
            )
            record.add_event(
                AnalysisEventType.TASK_FAILED,
                message="服务重启导致任务中断。",
            )
            self._persist(record)
        with self._lock:
            self._tasks[task_id] = record
        return record

    def list_tasks(self, limit: int = 20) -> list[dict[str, Any]]:
        """最近的任务文档；Mongo 不可用时退回内存里的任务。"""
        documents = task_repository.list_recent(limit)
        if documents:
            return documents
        with self._lock:
            records = sorted(
                self._tasks.values(), key=lambda item: item.created_at, reverse=True
            )[:limit]
        return [_record_document(record) for record in records]

    def cancel_task(self, task_id: str) -> bool:
        record = self.get_task(task_id)
        if record is None or record.status in FINISHED_STATUSES:
            return False
        record.cancel_requested = True
        return True

    def _emit_stage_completed(
        self,
        record: TaskRecord,
        stage: AnalysisStage,
        state: dict[str, Any],
    ) -> None:
        """阶段结束时把该阶段结果打包进事件。"""
        record.add_event(
            AnalysisEventType.STAGE_COMPLETED,
            stage=stage,
            message=f"{STAGE_LABEL[stage]}完成。",
            payload=_stage_payload(stage, record.request, state),
        )

    def _execute(self, record: TaskRecord) -> None:
        record.set_status(TaskStatus.RUNNING)
        record.add_event(AnalysisEventType.TASK_STARTED, message="开始执行多智能体分析链路。")
        record.add_event(
            AnalysisEventType.STAGE_STARTED,
            stage=AnalysisStage.INGEST,
            message="数据接入开始。",
        )
        self._persist(record)
        current_stage: AnalysisStage | None = AnalysisStage.INGEST
        state: dict[str, Any] = dict(initial_workflow_state(record.request, record.task_id))

        try:
            # debug 流会在节点开始前发出 task 事件，用它标记阶段开始，阶段耗时才准确
            for chunk in get_analysis_workflow().stream(state, stream_mode="debug"):
                if record.cancel_requested:
                    raise _TaskCancelled()
                chunk_type = chunk.get("type")
                chunk_payload = chunk.get("payload") or {}
                stage = NODE_STAGE.get(chunk_payload.get("name") or "")

                if chunk_type == "task" and stage is not None and stage != current_stage:
                    if current_stage is not None:
                        self._emit_stage_completed(record, current_stage, state)
                    current_stage = stage
                    record.add_event(
                        AnalysisEventType.STAGE_STARTED,
                        stage=stage,
                        message=f"{STAGE_LABEL[stage]}开始。",
                    )
                    self._persist(record)
                elif chunk_type == "task_result":
                    update = chunk_payload.get("result")
                    if isinstance(update, dict):
                        state.update(update)

            if record.cancel_requested:
                raise _TaskCancelled()
            if current_stage is not None:
                self._emit_stage_completed(record, current_stage, state)
                self._persist(record)

            record.result = build_run_response(record.request, state, record.task_id)
            record.set_status(TaskStatus.COMPLETED)
            record.add_event(AnalysisEventType.TASK_COMPLETED, message="分析完成。")
            self._persist(record)
        except _TaskCancelled:
            record.set_status(TaskStatus.CANCELLED)
            record.add_event(AnalysisEventType.TASK_CANCELLED, message="任务已取消。")
            self._persist(record)
        except (
            UnknownProviderError,
            LLMConfigurationError,
            LLMCallError,
            LookupError,
            ValueError,
        ) as exc:
            error = AnalysisError(code=_error_code(exc), message=str(exc))
            record.set_status(TaskStatus.FAILED, error=error)
            record.add_event(AnalysisEventType.TASK_FAILED, message=str(exc))
            self._persist(record)
        except Exception as exc:  # noqa: BLE001
            logger.exception("任务执行失败 %s", record.task_id)
            error = AnalysisError(code="internal_error", message="分析执行失败，请查看后端日志。")
            record.set_status(TaskStatus.FAILED, error=error)
            record.add_event(AnalysisEventType.TASK_FAILED, message=str(error.message))
            self._persist(record)


task_manager = TaskManager()
