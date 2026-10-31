"""协调各数据流并构建 Agent 初始分析上下文。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from agents.dataflows.fundamental_analyst import fundamental_dataflow
from agents.dataflows.market_analyst import market_dataflow
from agents.dataflows.news_sentiment_analyst import news_dataflow
from app.schemas.analysis_schemas import AnalysisTaskRequest, EvidenceItem

if TYPE_CHECKING:
    from agents.agent_state import AgentState


def build_initial_context(request: AnalysisTaskRequest) -> dict[str, Any]:
    """按任务周期和日期范围取数并组合证据，不依赖 LangGraph。"""
    code = request.stock_code
    period = request.period
    is_range_request = request.start_date is not None
    is_point_in_time_request = request.analysis_date is not None

    raw_kline = market_dataflow.fetch_kline_data(
        code=code,
        period=period,
        start_date=request.start_date,
        end_date=request.end_date,
    )
    requested_end_date = request.end_date or request.analysis_date
    kline_data, kline_evidence, actual_start_date, actual_end_date = (
        market_dataflow.prepare_kline_context(
            raw_kline=raw_kline,
            code=code,
            period=period,
            requested_start_date=request.start_date,
            requested_end_date=requested_end_date,
            analysis_date=request.analysis_date,
        )
    )

    market_snapshot: dict[str, Any] = {}
    fundamentals: dict[str, Any] = {}
    news: dict[str, Any] = {}
    evidence: list[EvidenceItem] = [kline_evidence]

    if is_range_request or is_point_in_time_request:
        # 历史任务按公开日期获取财务和新闻；实时估值快照不用于解释过去。
        data_start_date = request.start_date or request.analysis_date
        data_end_date = request.end_date or request.analysis_date
        fundamentals = fundamental_dataflow.fetch_historical_fundamentals(
            code=code,
            start_date=data_start_date,
            end_date=data_end_date,
        )
        news = news_dataflow.fetch_historical_news(
            code=code,
            start_date=data_start_date,
            end_date=data_end_date,
        )
        observed_at = datetime.now(timezone.utc)
        fundamental_evidence = fundamental_dataflow.build_historical_fundamental_evidence(
            fundamentals=fundamentals,
            observed_at=observed_at,
        )
        news_evidence = news_dataflow.build_news_evidence(news, observed_at)
        evidence.extend(
            item
            for item in (fundamental_evidence, news_evidence)
            if item is not None
        )
    else:
        # 未指定历史日期时，使用当前行情、基本面和近期新闻快照。
        snapshot = market_dataflow.fetch_current_snapshot(code)
        observed_at = datetime.now(timezone.utc)
        snapshot_meta = snapshot.get("meta") or {}
        source_note = snapshot_meta.get("note")

        market_snapshot = market_dataflow.extract_market_snapshot(snapshot)
        fundamentals = fundamental_dataflow.extract_fundamentals(snapshot)
        news = news_dataflow.build_current_news_data(news_dataflow.extract_news(snapshot))

        market_evidence = market_dataflow.build_market_snapshot_evidence(
            market_data=market_snapshot,
            observed_at=observed_at,
            source_note=source_note,
        )
        fundamental_evidence = fundamental_dataflow.build_fundamental_evidence(
            fundamentals=fundamentals,
            observed_at=observed_at,
            source_note=source_note,
        )
        news_evidence = news_dataflow.build_news_evidence(news, observed_at)

        evidence.extend(
            item
            for item in (market_evidence, fundamental_evidence, news_evidence)
            if item is not None
        )

    return {
        "stock_code": code,
        "analysis_period": period,
        "analysis_date": actual_end_date,
        "requested_analysis_date": request.analysis_date,
        "requested_start_date": request.start_date,
        "requested_end_date": requested_end_date,
        "actual_start_date": actual_start_date,
        "actual_end_date": actual_end_date,
        "market_snapshot": market_snapshot,
        "fundamentals_data": fundamentals,
        "news_data": news,
        "kline_data": kline_data,
        "evidence": evidence,
    }


def build_initial_agent_state(request: AnalysisTaskRequest, task_id: str) -> AgentState:
    """将数据接入上下文包装成 LangGraph 的共享状态。"""
    from agents.agent_state import AgentState
    from app.schemas.analysis_schemas import AnalysisStage

    context = build_initial_context(request)
    return AgentState(
        messages=[],
        task_id=task_id,
        sender="data_ingestion",
        current_stage=AnalysisStage.INGEST,
        **context,
        investment_debate_state={
            "bull_history": [],
            "bear_history": [],
            "history": [],
            "current_speaker": "bull",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        },
        risk_debate_state={
            "aggressive_history": [],
            "neutral_history": [],
            "conservative_history": [],
            "history": [],
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        },
        tool_call_counts={"market": 0, "fundamental": 0, "news": 0},
        errors=[],
    )
