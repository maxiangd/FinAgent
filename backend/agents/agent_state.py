"""LangGraph 节点间传递的共享状态。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, TypedDict

from langgraph.graph import MessagesState

from app.schemas.analysis_schemas import (
    AnalysisError,
    AnalysisStage,
    AnalystFinding,
    DebateTurn,
    EvidenceItem,
    MarketAnalystReport,
    PMDecision,
    RiskReview,
    TradeProposal,
)


class InvestmentDebateState(TypedDict, total=False):
    """多空研究员辩论的过程状态。"""

    bull_history: list[str]
    bear_history: list[str]
    history: list[DebateTurn]
    current_speaker: Literal["bull", "bear"]
    current_response: str
    judge_decision: str
    count: int


class RiskDebateState(TypedDict, total=False):
    """进攻、中性、保守风控角色的讨论状态。"""

    aggressive_history: list[str]
    neutral_history: list[str]
    conservative_history: list[str]
    history: list[RiskReview]
    latest_speaker: Literal["aggressive", "neutral", "conservative"]
    current_response: str
    judge_decision: str
    count: int


class AgentState(MessagesState, total=False):
    """分析任务在各个 LangGraph 节点之间流转的共享状态。"""

    task_id: str
    stock_code: str
    analysis_period: Literal["daily", "weekly", "monthly"]
    analysis_date: date | None
    requested_analysis_date: date | None
    requested_start_date: date | None
    requested_end_date: date | None
    actual_start_date: date | None
    actual_end_date: date | None
    sender: str
    current_stage: AnalysisStage
    market_snapshot: dict[str, Any]
    fundamentals_data: dict[str, Any]
    news_data: dict[str, Any]
    kline_data: dict[str, Any]
    evidence: list[EvidenceItem]
    market_report: MarketAnalystReport
    fundamentals_report: AnalystFinding
    news_report: AnalystFinding
    investment_debate_state: InvestmentDebateState
    investment_plan: str
    trade_proposal: TradeProposal
    risk_debate_state: RiskDebateState
    pm_decision: PMDecision
    tool_call_counts: dict[str, int]
    errors: list[AnalysisError]
