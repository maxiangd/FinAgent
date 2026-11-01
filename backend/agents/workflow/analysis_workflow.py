"""按固定顺序执行的分析工作流：数据接入 → 行情 → 基本面 → 新闻情绪分析师。

后续阶段（多空辩论、交易提案、风控、PM 决策）以同样的方式挂到这张图上，
由节点之间连边或加条件边控制流转。
"""

from __future__ import annotations

import threading
from typing import Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from agents.agent_state import AgentState
from agents.analysis_context_builder import build_initial_context
from agents.roles.analysts.fundamental_analyst_agent import fundamental_analyst_node
from agents.roles.analysts.market_analyst_agent import market_analyst_node
from agents.roles.analysts.news_sentiment_analyst_agent import news_sentiment_analyst_node
from agents.roles.managers.portfolio_manager_agent import portfolio_manager_node
from agents.roles.researchers.debate_researchers import (
    bear_researcher_node,
    bull_researcher_node,
    debate_should_continue,
)
from agents.roles.risk_mgmt.risk_review_agents import (
    aggressive_risk_node,
    conservative_risk_node,
    neutral_risk_node,
)
from agents.roles.trader.trader_agent import trade_proposal_node
from app.schemas.analysis_schemas import AnalysisStage, AnalysisTaskRequest


def _request_from_state(state: dict[str, Any]) -> AnalysisTaskRequest:
    """从共享状态还原任务请求，供数据接入节点使用。"""
    return AnalysisTaskRequest(
        stock_code=state["stock_code"],
        period=state["analysis_period"],
        start_date=state.get("requested_start_date"),
        end_date=state.get("requested_end_date"),
        analysis_date=state.get("requested_analysis_date"),
        provider=state.get("provider"),
    )


def load_context_node(state: dict[str, Any]) -> dict[str, Any]:
    """数据接入节点：按任务区间取数并生成证据。"""
    request = _request_from_state(state)
    context = build_initial_context(request)
    return {
        **context,
        "sender": "data_ingestion",
        "current_stage": AnalysisStage.INGEST,
    }


ANALYST_STEPS = (
    ("market_analyst", market_analyst_node),
    ("fundamental_analyst", fundamental_analyst_node),
    ("news_sentiment_analyst", news_sentiment_analyst_node),
)

_workflow = None
_workflow_lock = threading.Lock()


def build_analysis_workflow():
    """固定链路：数据接入 → 三个分析师（串行）→ 辩论 → 提案 → 风控 → PM。"""
    graph = StateGraph(AgentState)
    graph.add_node("load_context", load_context_node)
    graph.add_edge(START, "load_context")

    # 串行而非并行：免费模型并发受限，串行也更利于阶段事件按顺序推送
    previous = "load_context"
    for node_name, node_fn in ANALYST_STEPS:
        graph.add_node(node_name, node_fn)
        graph.add_edge(previous, node_name)
        previous = node_name

    graph.add_node("bull_researcher", bull_researcher_node)
    graph.add_node("bear_researcher", bear_researcher_node)
    graph.add_node("trader", trade_proposal_node)
    graph.add_node("aggressive_risk", aggressive_risk_node)
    graph.add_node("neutral_risk", neutral_risk_node)
    graph.add_node("conservative_risk", conservative_risk_node)
    graph.add_node("portfolio_manager", portfolio_manager_node)

    graph.add_edge(previous, "bull_researcher")
    graph.add_edge("bull_researcher", "bear_researcher")
    # 发言计数达到上限后离开辩论循环
    graph.add_conditional_edges(
        "bear_researcher",
        debate_should_continue,
        {"continue_debate": "bull_researcher", "end_debate": "trader"},
    )
    graph.add_edge("trader", "aggressive_risk")
    graph.add_edge("aggressive_risk", "neutral_risk")
    graph.add_edge("neutral_risk", "conservative_risk")
    graph.add_edge("conservative_risk", "portfolio_manager")
    graph.add_edge("portfolio_manager", END)
    return graph.compile()


def get_analysis_workflow():
    """返回进程内复用的已编译工作流。"""
    global _workflow
    if _workflow is None:
        with _workflow_lock:
            if _workflow is None:
                _workflow = build_analysis_workflow()
    return _workflow


def initial_workflow_state(
    request: AnalysisTaskRequest,
    task_id: str | None = None,
) -> AgentState:
    """构造图的输入状态：只包含任务参数，数据由 load_context 节点获取。"""
    return AgentState(
        messages=[],
        task_id=task_id or uuid4().hex,
        stock_code=request.stock_code,
        analysis_period=request.period,
        analysis_date=request.analysis_date,
        requested_analysis_date=request.analysis_date,
        requested_start_date=request.start_date,
        requested_end_date=request.end_date,
        provider=request.provider,
        current_stage=AnalysisStage.INGEST,
        evidence=[],
        errors=[],
        tool_call_counts={},
    )
