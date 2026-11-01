"""三类风控评审：进攻 / 中性 / 保守，对交易提案做第二层评审。"""

from __future__ import annotations

from typing import Any, Mapping

from agents.roles.analysts.tool_agent_runtime import run_structured_completion
from agents.llm_provider_client import load_llm_settings
from agents.research_context import (
    build_analysis_summary,
    debate_transcript,
    trade_proposal_summary,
)
from app.schemas.analysis_schemas import AnalysisStage, RiskReview

_SYSTEM_PROMPT = """你是 FinAgent 的{profile_name}，对交易提案做第二层评审。
只依据输入的分析师结论、辩论记录、交易提案和证据目录，不编造数据。
必须引用证据目录中的 id。
decision 只能是 approve、revise、reject 三个英文单词之一（通过 / 需要修改 / 否决），
不要使用 buy、sell、hold、reduce、avoid 这类交易动作词。
required_controls 写具体可执行的风控约束（如仓位上限、止损条件）；没有则留空数组。
最终只返回一个 JSON 对象，字段为：
reviewer (固定为 "{reviewer}"), decision, summary (string),
concerns (string array), required_controls (string array)。"""

_RISK_PROFILES = {
    "aggressive": ("进攻型风控", "更关注机会与收益空间，但必须给出明确的风险边界。"),
    "neutral": ("中性风控", "在收益与风险之间取平衡，既不过度保守也不忽视回撤。"),
    "conservative": ("保守型风控", "以本金安全为第一优先，对回撤和不确定性更严格。"),
}


def _run_risk_review(state: Mapping[str, Any], reviewer: str) -> dict[str, Any]:
    settings = load_llm_settings(state.get("provider"))
    risk_state = dict(state.get("risk_debate_state") or {})
    history = list(risk_state.get("history") or [])
    profile_name, profile_instruction = _RISK_PROFILES[reviewer]

    payload = build_analysis_summary(state)
    payload["trade_proposal"] = trade_proposal_summary(state.get("trade_proposal"))
    payload["debate_history"] = debate_transcript(state)
    payload["profile_instruction"] = profile_instruction
    payload["previous_reviews"] = [
        {"reviewer": review.reviewer, "decision": review.decision, "summary": review.summary}
        for review in history
    ]

    review = run_structured_completion(
        settings=settings,
        system_prompt=_SYSTEM_PROMPT.format(profile_name=profile_name, reviewer=reviewer),
        payload=payload,
        model_cls=RiskReview,
    )
    review = review.model_copy(
        update={
            "reviewer": reviewer,
            "concerns": review.concerns[:5],
            "required_controls": review.required_controls[:5],
        }
    )
    history.append(review)
    updated = {
        **risk_state,
        "history": history,
        "count": len(history),
        "latest_speaker": reviewer,
        "current_response": review.summary,
    }
    return {
        "risk_debate_state": updated,
        "sender": f"{reviewer}_risk",
        "current_stage": AnalysisStage.RISK,
    }


def aggressive_risk_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """进攻型风控节点。"""
    return _run_risk_review(state, "aggressive")


def neutral_risk_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """中性风控节点。"""
    return _run_risk_review(state, "neutral")


def conservative_risk_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """保守型风控节点。"""
    return _run_risk_review(state, "conservative")
