"""PM（投资组合经理）：汇总分析师、辩论、提案与风控，输出最终研究结论。"""

from __future__ import annotations

from typing import Any, Mapping

from agents.roles.analysts.tool_agent_runtime import run_structured_completion
from agents.llm_provider_client import load_llm_settings
from agents.research_context import (
    allowed_evidence_ids,
    build_analysis_summary,
    debate_transcript,
    sanitize_evidence_ids,
    trade_proposal_summary,
)
from app.schemas.analysis_schemas import AnalysisStage, PMDecision

_SYSTEM_PROMPT = """你是 FinAgent 的 PM（投资组合经理）。
你需要汇总三位分析师的结论、多空辩论、交易提案和三类风控评审，给出最终研究结论。
这不是投资建议，也不是真实交易指令，只用于研究演示。
只能依据输入数据判断，不要编造事实或价位；引用证据时必须使用证据目录中的 id。
风控意见与提案冲突时，以风控要求为先，并在 rationale 中说明取舍。
把握不足时降低 confidence。
最终只返回一个 JSON 对象，字段为：
action (buy/hold/reduce/avoid), rationale (string), confidence (0 到 1),
key_risks (string array), evidence_ids (string array)。"""


def portfolio_manager_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """PM 节点：输出 PMDecision。"""
    settings = load_llm_settings(state.get("provider"))
    risk_state = state.get("risk_debate_state") or {}

    payload = build_analysis_summary(state)
    payload["debate_history"] = debate_transcript(state)
    payload["trade_proposal"] = trade_proposal_summary(state.get("trade_proposal"))
    payload["risk_reviews"] = [
        {
            "reviewer": review.reviewer,
            "decision": review.decision,
            "summary": review.summary,
            "concerns": review.concerns,
            "required_controls": review.required_controls,
        }
        for review in (risk_state.get("history") or [])
    ]

    decision = run_structured_completion(
        settings=settings,
        system_prompt=_SYSTEM_PROMPT,
        payload=payload,
        model_cls=PMDecision,
    )
    decision = decision.model_copy(
        update={"evidence_ids": sanitize_evidence_ids(decision.evidence_ids, allowed_evidence_ids(state))}
    )
    return {
        "pm_decision": decision,
        "sender": "portfolio_manager",
        "current_stage": AnalysisStage.PM,
    }
