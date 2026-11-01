"""多空双研究员：按轮次交替发言，发言计数达到上限后交给交易员。"""

from __future__ import annotations

from typing import Any, Mapping

from agents.roles.analysts.tool_agent_runtime import run_structured_completion
from agents.llm_provider_client import load_agent_settings
from agents.research_context import (
    allowed_evidence_ids,
    build_analysis_summary,
    debate_transcript,
    sanitize_evidence_ids,
)
from app.schemas.analysis_schemas import AnalysisStage, DebateTurn

# 每个研究员各发言 3 次，共 6 条发言
DEBATE_ROUNDS = 3

_SYSTEM_PROMPT = """你是 FinAgent 的{role_name}，参与针对同一只股票的多空辩论。
只依据输入的分析师结论、证据目录和已有发言，不编造数据或新闻。
必须引用证据目录中的 id；没有证据支撑的观点要明确说明是推断。
发言要针对对手上一轮的具体论点做出回应，不要重复自己已说过的内容。
不要给出买入或卖出指令，只陈述判断与理由。
最终只返回一个 JSON 对象，字段为：
round_number (整数), speaker (固定为 "{speaker}"), argument (string), evidence_ids (string array)。"""

_ROLE_PROMPTS = {
    "bull": ("多头研究员", "你的立场是看多：寻找支撑上涨的论据，并反驳空头观点。"),
    "bear": ("空头研究员", "你的立场是看空：寻找下行风险，并反驳多头观点。"),
}


def _run_researcher(state: Mapping[str, Any], role: str) -> dict[str, Any]:
    """执行一次研究员发言，并把发言追加进辩论状态。"""
    settings = load_agent_settings(state, f"{role}_researcher")
    debate = dict(state.get("investment_debate_state") or {})
    history = list(debate.get("history") or [])
    round_number = len(history) // 2 + 1

    role_name, stance_instruction = _ROLE_PROMPTS[role]
    payload = build_analysis_summary(state)
    payload.update(
        {
            "round_number": round_number,
            "your_role": role,
            "stance_instruction": stance_instruction,
            "debate_history": debate_transcript(state),
        }
    )

    turn = run_structured_completion(
        settings=settings,
        system_prompt=_SYSTEM_PROMPT.format(role_name=role_name, speaker=role),
        payload=payload,
        model_cls=DebateTurn,
    )
    # 轮次和发言人以代码为准，避免模型自述错位
    turn = turn.model_copy(
        update={
            "round_number": round_number,
            "speaker": role,
            "evidence_ids": sanitize_evidence_ids(turn.evidence_ids, allowed_evidence_ids(state)),
        }
    )

    history.append(turn)
    updated = {
        **debate,
        "history": history,
        "count": len(history),
        "current_speaker": "bear" if role == "bull" else "bull",
        "current_response": turn.argument,
    }
    key = f"{role}_history"
    updated[key] = list(debate.get(key) or []) + [turn.argument]
    return {
        "investment_debate_state": updated,
        "sender": f"{role}_researcher",
        "current_stage": AnalysisStage.DEBATE,
    }


def bull_researcher_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """多头研究员节点。"""
    return _run_researcher(state, "bull")


def bear_researcher_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """空头研究员节点。"""
    return _run_researcher(state, "bear")


def debate_should_continue(state: Mapping[str, Any]) -> str:
    """发言计数达到 2 × 轮数后结束辩论，否则继续让多头发言。"""
    debate = state.get("investment_debate_state") or {}
    if int(debate.get("count") or 0) >= DEBATE_ROUNDS * 2:
        return "end_debate"
    return "continue_debate"
