"""交易员：把分析师结论与辩论结果整理成研究性交易提案。"""

from __future__ import annotations

from typing import Any, Mapping

from agents.roles.analysts.tool_agent_runtime import run_structured_completion
from agents.llm_provider_client import load_llm_settings
from agents.research_context import (
    allowed_evidence_ids,
    build_analysis_summary,
    debate_transcript,
    sanitize_evidence_ids,
)
from app.schemas.analysis_schemas import AnalysisStage, TradeProposal

_SYSTEM_PROMPT = """你是 FinAgent 的交易员。基于分析师结论和多空辩论，提出一份研究性的交易提案。
这不是真实下单指令，只用于研究演示。
只能使用输入中的事实和证据，不要编造价位、事件或理由。
给出的价格必须能从证据或分析结论中找到依据；无法确定时填 null。
必须引用证据目录中的 id。
最终只返回一个 JSON 对象，字段为：
action (buy/hold/reduce/avoid), rationale (string),
entry_price / target_price / stop_price (number 或 null), evidence_ids (string array)。"""


def trade_proposal_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """交易员节点：输出 TradeProposal。"""
    settings = load_llm_settings(state.get("provider"))
    payload = build_analysis_summary(state)
    payload["debate_history"] = debate_transcript(state)

    proposal = run_structured_completion(
        settings=settings,
        system_prompt=_SYSTEM_PROMPT,
        payload=payload,
        model_cls=TradeProposal,
    )
    proposal = proposal.model_copy(
        update={"evidence_ids": sanitize_evidence_ids(proposal.evidence_ids, allowed_evidence_ids(state))}
    )
    return {
        "trade_proposal": proposal,
        "sender": "trader",
        "current_stage": AnalysisStage.TRADER,
    }
