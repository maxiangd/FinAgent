"""多智能体分析任务与阶段结果的数据模型。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    """分析任务的生命周期状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisStage(str, Enum):
    """前端展示的分析阶段标识。"""

    INGEST = "ingest"
    ANALYST = "analyst"
    DEBATE = "debate"
    TRADER = "trader"
    RISK = "risk"
    PM = "pm"


class AnalysisEventType(str, Enum):
    """任务和阶段执行过程中可推送的事件类型。"""

    TASK_QUEUED = "task_queued"
    TASK_STARTED = "task_started"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    STAGE_FAILED = "stage_failed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_CANCELLED = "task_cancelled"
    HEARTBEAT = "heartbeat"


class AnalysisTaskRequest(BaseModel):
    """创建一次股票分析任务的请求。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stock_code: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="六位 A 股代码，例如 600519",
    )
    period: Literal["daily", "weekly", "monthly"] = Field(
        default="daily",
        description="分析使用的 K 线周期",
    )
    start_date: date | None = Field(
        default=None,
        description="分析区间开始日期；与结束日期同时提供",
    )
    end_date: date | None = Field(
        default=None,
        description="分析区间结束日期；与开始日期同时提供",
    )
    analysis_date: date | None = Field(
        default=None,
        description="兼容单一基准日期的旧请求；不传区间时使用最新数据",
    )

    @model_validator(mode="after")
    def validate_analysis_dates(self):
        """检查日期区间完整、顺序正确且不包含未来日期。"""
        has_start = self.start_date is not None
        has_end = self.end_date is not None
        if has_start != has_end:
            raise ValueError("start_date 和 end_date 必须同时提供")
        if has_start and self.analysis_date is not None:
            raise ValueError("日期区间和 analysis_date 不能同时提供")
        if has_start and self.start_date > self.end_date:
            raise ValueError("start_date 不能晚于 end_date")
        if self.end_date and self.end_date > date.today():
            raise ValueError("end_date 不能晚于今天")
        if self.analysis_date and self.analysis_date > date.today():
            raise ValueError("analysis_date 不能晚于今天")
        return self


class AnalysisTaskStatusResponse(BaseModel):
    """供前端查询的任务状态。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    stock_code: str
    analysis_period: Literal["daily", "weekly", "monthly"] | None = None
    requested_start_date: date | None = None
    requested_end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    analysis_date: date | None = None
    status: TaskStatus
    current_stage: AnalysisStage | None = None
    progress: int = Field(default=0, ge=0, le=100)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AnalysisEvent(BaseModel):
    """通过 SSE 推送给前端的任务事件。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: uuid4().hex)
    task_id: str
    event_type: AnalysisEventType
    stage: AnalysisStage | None = None
    agent_name: str | None = None
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class AnalysisError(BaseModel):
    """分析任务或节点执行失败时返回的结构化错误。"""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    stage: AnalysisStage | None = None
    retryable: bool = False


class EvidenceItem(BaseModel):
    """分析结论引用的一项外部数据或计算结果。"""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(default_factory=lambda: uuid4().hex)
    category: Literal["market", "fundamental", "news", "technical", "other"]
    source: str = Field(description="数据来源，例如 akshare 或新闻媒体名称")
    observed_at: datetime | date | None = None
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class AnalystFinding(BaseModel):
    """单个分析师的结构化结论。"""

    model_config = ConfigDict(extra="forbid")

    analyst: Literal["market", "fundamental", "news"]
    stance: Literal["bullish", "neutral", "bearish"]
    conclusion: str
    key_points: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class DebateTurn(BaseModel):
    """多空辩论中的一轮发言。"""

    model_config = ConfigDict(extra="forbid")

    round_number: int = Field(ge=1)
    speaker: Literal["bull", "bear"]
    argument: str
    evidence_ids: list[str] = Field(default_factory=list)


class TradeProposal(BaseModel):
    """交易研究提案，不代表实际下单指令。"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["buy", "hold", "reduce", "avoid"]
    rationale: str
    entry_price: float | None = Field(default=None, gt=0)
    target_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    evidence_ids: list[str] = Field(default_factory=list)


class RiskReview(BaseModel):
    """一个风控角色对提案的审查结果。"""

    model_config = ConfigDict(extra="forbid")

    reviewer: Literal["aggressive", "neutral", "conservative"]
    decision: Literal["approve", "revise", "reject"]
    summary: str
    concerns: list[str] = Field(default_factory=list)
    required_controls: list[str] = Field(default_factory=list)


class PMDecision(BaseModel):
    """PM 汇总分析与风控结果后的最终研究结论。"""

    model_config = ConfigDict(extra="forbid")

    action: Literal["buy", "hold", "reduce", "avoid"]
    rationale: str
    confidence: float = Field(ge=0, le=1)
    key_risks: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class AnalysisReport(BaseModel):
    """一次分析任务的可持久化最终报告。"""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    stock_code: str
    analysis_period: Literal["daily", "weekly", "monthly"] | None = None
    requested_start_date: date | None = None
    requested_end_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    analysis_date: date | None = None
    status: TaskStatus
    evidence: list[EvidenceItem] = Field(default_factory=list)
    analyst_findings: list[AnalystFinding] = Field(default_factory=list)
    debate_turns: list[DebateTurn] = Field(default_factory=list)
    trade_proposal: TradeProposal | None = None
    risk_reviews: list[RiskReview] = Field(default_factory=list)
    pm_decision: PMDecision | None = None
    error: AnalysisError | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    completed_at: datetime | None = None
