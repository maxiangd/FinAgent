"""交易员：把分析师结论与辩论结果整理成研究性交易提案。"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from agents.roles.analysts.tool_agent_runtime import run_structured_completion
from agents.llm_provider_client import load_agent_settings
from agents.price_levels import target_and_stop
from agents.research_context import (
    allowed_evidence_ids,
    build_analysis_summary,
    debate_transcript,
    sanitize_evidence_ids,
)
from app.schemas.analysis_schemas import AnalysisStage, TradeProposal

logger = logging.getLogger("finagent.trader")

_SYSTEM_PROMPT = """你是 FinAgent 的交易员。基于分析师结论和多空辩论，提出一份研究性的交易提案。
这不是真实下单指令，只用于研究演示。
只能使用输入中的事实和证据，不要编造事件或数据。
三个价位必须都给出（单位：元，大于 0），并与 action 方向一致：
- entry_price 成交价：买入提案为买入价，减仓/回避提案为卖出价；通常取最新收盘价或附近技术位；
- target_price 目标价：买入提案为预期卖出的价位（高于成交价），减仓/回避提案为预期回补的价位（低于成交价）；
- stop_price 止损价：判断失效的价位，买入提案低于成交价，减仓/回避提案高于成交价。
价位要能对应到证据目录中的区间高低点、均线或最新价格；缺少数值时可基于区间边界估算，并在 rationale 中说明是技术位参考。
必须引用证据目录中的 id。
最终只返回一个 JSON 对象，字段为：
action (buy/hold/reduce/avoid), rationale (string),
entry_price / target_price / stop_price (number), evidence_ids (string array)。"""


def _fill_missing_prices(proposal: TradeProposal, context: Mapping[str, Any]) -> TradeProposal:
    """补齐或纠正价位：目标价、止损价必须分别落在成交价的两侧，且两价不能相同。"""
    items = (context.get("kline_data") or {}).get("items") or []
    closes = [float(bar["close"]) for bar in items if bar.get("close") is not None]
    if not closes:
        return proposal

    entry = proposal.entry_price or round(closes[-1], 2)
    bullish = proposal.action in ("buy", "hold")
    fallback_target, fallback_stop = target_and_stop(context, bullish)

    def valid(value: float | None, above: bool) -> bool:
        return value is not None and (value > entry if above else value < entry)

    def pick(value: float | None, above: bool, fallback: float | None) -> float | None:
        if valid(value, above):
            return value
        return fallback if valid(fallback, above) else None

    target = pick(proposal.target_price, bullish, fallback_target)
    stop = pick(proposal.stop_price, not bullish, fallback_stop)

    if (entry, target, stop) == (proposal.entry_price, proposal.target_price, proposal.stop_price):
        return proposal
    logger.warning(
        "%s 交易提案价位缺失或方向矛盾，已按近期 K 线估算：entry=%s target=%s stop=%s",
        proposal.action,
        entry,
        target,
        stop,
    )
    return proposal.model_copy(
        update={
            "entry_price": entry,
            "target_price": target,
            "stop_price": stop,
            "prices_estimated": True,
        }
    )


def trade_proposal_node(state: Mapping[str, Any]) -> dict[str, Any]:
    """交易员节点：输出 TradeProposal。"""
    settings = load_agent_settings(state, "trader")
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
    proposal = _fill_missing_prices(proposal, state)
    return {
        "trade_proposal": proposal,
        "sender": "trader",
        "current_stage": AnalysisStage.TRADER,
    }
