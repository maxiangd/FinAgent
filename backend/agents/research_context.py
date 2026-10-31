"""把分析师结论与证据整理成下游角色（研究员、交易员、风控、PM）的输入。"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from app.schemas.analysis_schemas import AnalystFinding, EvidenceItem, MarketAnalystReport


def _market_summary(report: MarketAnalystReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "stance": report.stance,
        "conclusion": report.conclusion,
        "key_points": [point.text for point in report.key_points],
        "confidence": report.confidence,
        "data_gaps": report.data_gaps,
    }


def _finding_summary(finding: AnalystFinding | None) -> dict[str, Any] | None:
    if finding is None:
        return None
    return {
        "stance": finding.stance,
        "conclusion": finding.conclusion,
        "key_points": finding.key_points,
        "confidence": finding.confidence,
    }


def evidence_catalog(items: Iterable[EvidenceItem]) -> list[dict[str, Any]]:
    """证据目录：只保留可引用所需的字段，避免把原始数据塞进提示词。"""
    catalog = []
    for item in items:
        catalog.append(
            {
                "id": item.evidence_id,
                "category": item.category,
                "source": item.source,
                "observed_at": str(item.observed_at)[:10] if item.observed_at else None,
                "summary": item.summary[:200],
            }
        )
    return catalog


def allowed_evidence_ids(state: Mapping[str, Any]) -> set[str]:
    return {
        item.evidence_id
        for item in (state.get("evidence") or [])
        if isinstance(item, EvidenceItem)
    }


def sanitize_evidence_ids(ids: Iterable[str], allowed: set[str]) -> list[str]:
    """丢弃不存在的证据 ID，保持顺序去重。"""
    seen: set[str] = set()
    result = []
    for evidence_id in ids:
        if evidence_id in allowed and evidence_id not in seen:
            seen.add(evidence_id)
            result.append(evidence_id)
    return result


def build_analysis_summary(state: Mapping[str, Any]) -> dict[str, Any]:
    """汇总三个分析师的结论、证据目录与数据限制。"""
    kline = state.get("kline_data") or {}
    evidence = [item for item in (state.get("evidence") or []) if isinstance(item, EvidenceItem)]
    limitations = sorted({limitation for item in evidence for limitation in item.limitations})
    return {
        "stock_code": state.get("stock_code"),
        "stock_name": kline.get("name"),
        "period": state.get("analysis_period"),
        "analysis_range": {
            "start": kline.get("actual_start_date"),
            "end": kline.get("actual_end_date"),
        },
        "analyst_reports": {
            "market": _market_summary(state.get("market_report")),
            "fundamental": _finding_summary(state.get("fundamentals_report")),
            "news": _finding_summary(state.get("news_report")),
        },
        "evidence": evidence_catalog(evidence),
        "data_limitations": limitations,
    }


def debate_transcript(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """把辩论状态转成可放进提示词的记录。"""
    debate = state.get("investment_debate_state") or {}
    history = debate.get("history") or []
    return [
        {
            "round": turn.round_number,
            "speaker": turn.speaker,
            "argument": turn.argument,
        }
        for turn in history
    ]


def trade_proposal_summary(proposal) -> dict[str, Any] | None:
    """交易提案的精简表示，供风控和 PM 使用。"""
    if proposal is None:
        return None
    return {
        "action": proposal.action,
        "rationale": proposal.rationale,
        "entry_price": proposal.entry_price,
        "target_price": proposal.target_price,
        "stop_price": proposal.stop_price,
    }
