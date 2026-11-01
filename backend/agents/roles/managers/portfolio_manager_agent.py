"""PM（投资组合经理）：汇总分析师、辩论、提案与风控，输出最终研究结论。"""

from __future__ import annotations

from typing import Any, Mapping

from agents.roles.analysts.tool_agent_runtime import run_structured_completion
from agents.llm_provider_client import load_agent_settings
from agents.price_levels import target_and_stop
from agents.research_context import (
    allowed_evidence_ids,
    build_analysis_summary,
    debate_transcript,
    sanitize_evidence_ids,
    trade_proposal_summary,
)
from app.schemas.analysis_schemas import AnalysisStage, PMDecision, TradeProposal

_SYSTEM_PROMPT = """你是 FinAgent 的 PM（投资组合经理）。
你需要汇总三位分析师的结论、多空辩论、交易提案和三类风控评审，给出最终研究结论。
这不是投资建议，也不是真实交易指令，只用于研究演示。
只能依据输入数据判断，不要编造事实或价位；引用证据时必须使用证据目录中的 id。
风控意见与提案冲突时，以风控要求为先，并在 rationale 中说明取舍。
把握不足时降低 confidence。
如果能从证据中确定价位，请补充 target_price 和 stop_price（单位：元，必须大于 0）：
- buy / hold：target_price 为目标价，应高于当前价；stop_price 为止损价，应低于当前价；
- reduce / avoid：target_price 为预期回补或卖出参考价，应低于当前价；stop_price 为判断失效价，应高于当前价。
价位必须对应证据目录中的区间高低点、均线或最新价格；无法确定时留空。
target_price 不能等于 stop_price，也不要把两者都放在当前价的同一侧。
最终只返回一个 JSON 对象，字段为：
action (buy/hold/reduce/avoid), rationale (string), confidence (0 到 1),
target_price (number, 可空), stop_price (number, 可空),
key_risks (string array), evidence_ids (string array)。"""


def _normalize_prices(
    decision: PMDecision,
    proposal: TradeProposal | None,
    context: Mapping[str, Any] | None = None,
) -> PMDecision:
    """按最新收盘价校验价位：买入/持有要求目标价高于现价、止损价低于现价，减仓/回避相反。

    模型给出的价位不满足条件（含两价相同）时，依次退回交易提案和近期 K 线估算值；
    仍然无法给出合理价位时留空，避免展示自相矛盾的结论。
    """
    items = (context or {}).get("kline_data", {}).get("items") or []
    closes = [float(item["close"]) for item in items if item.get("close") is not None]
    reference = closes[-1] if closes else None
    bullish = decision.action in ("buy", "hold")

    target = decision.target_price
    stop = decision.stop_price
    proposal_target = proposal.target_price if proposal else None
    proposal_stop = proposal.stop_price if proposal else None

    if reference is None:
        target = target if target is not None else proposal_target
        stop = stop if stop is not None else proposal_stop
        if target is not None and stop is not None:
            if (bullish and target < stop) or (not bullish and target > stop):
                target, stop = stop, target
    else:
        fallback_target, fallback_stop = target_and_stop(context, bullish)

        def valid(candidate, above):
            return candidate is not None and (
                candidate > reference if above else candidate < reference
            )

        target = (
            target
            if valid(target, bullish)
            else proposal_target
            if valid(proposal_target, bullish)
            else fallback_target
        )
        if not valid(target, bullish):
            target = None
        stop = (
            stop
            if valid(stop, not bullish)
            else proposal_stop
            if valid(proposal_stop, not bullish)
            else fallback_stop
        )
        if not valid(stop, not bullish):
            stop = None

    estimated = (target, stop) != (decision.target_price, decision.stop_price)
    if not estimated and proposal is not None and proposal.prices_estimated:
        estimated = True
    return decision.model_copy(
        update={
            "target_price": target,
            "stop_price": stop,
            "prices_estimated": estimated,
        }
    )


def portfolio_manager_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """PM 节点：输出 PMDecision。"""
    settings = load_agent_settings(state, "portfolio_manager")
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
    decision = _normalize_prices(
        decision, state.get("trade_proposal"), state
    )
    return {
        "pm_decision": decision,
        "sender": "portfolio_manager",
        "current_stage": AnalysisStage.PM,
    }
