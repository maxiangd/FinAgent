"""整理当前基本面快照或按公告日期回溯的财务数据。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

from app.schemas.analysis_schemas import EvidenceItem
from data_sources.analysis.fundamental_data_service import get_historical_fundamentals


_FUNDAMENTAL_FIELDS = (
    "industry",
    "marketCap",
    "pe",
    "pb",
    "roe",
    "revGrowth",
    "profitGrowth",
    "margin",
    "dividendYield",
)


def extract_fundamentals(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """提取行业、估值、盈利能力、增长和股息率字段。"""
    if not snapshot:
        return {}
    return {key: snapshot[key] for key in _FUNDAMENTAL_FIELDS if key in snapshot}


def fetch_historical_fundamentals(
    code: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """获取按报告披露日整理的区间基本面数据。"""
    return get_historical_fundamentals(code, start_date, end_date)


def build_fundamental_evidence(
    fundamentals: Mapping[str, Any],
    observed_at: datetime,
    source_note: str | None = None,
) -> EvidenceItem | None:
    """为当前基本面数据建立证据，并注明其不是历史时点数据。"""
    if not fundamentals or not any(value is not None for value in fundamentals.values()):
        return None
    limitations = [
        "基本面字段没有独立的披露日期；记录时间表示读取当前快照的时间。",
        "该快照不能代表过去某个日期当时已公开的财务数据。",
    ]
    if source_note:
        limitations.append(f"数据源说明：{source_note}")
    return EvidenceItem(
        category="fundamental",
        source="财务与估值快照（新浪、腾讯、巨潮）",
        observed_at=observed_at,
        summary="当前可获取的行业、估值与财务指标。",
        data=dict(fundamentals),
        limitations=limitations,
    )


def build_historical_fundamental_evidence(
    fundamentals: Mapping[str, Any],
    observed_at: datetime,
) -> EvidenceItem | None:
    """为历史基本面建立保留报告期和公告日期的证据。"""
    baseline = fundamentals.get("baseline")
    reports = fundamentals.get("reports_in_range") or []
    limitations = list(fundamentals.get("limitations") or [])
    if not baseline and not reports and not limitations:
        return None
    return EvidenceItem(
        category="fundamental",
        source="新浪历史财务指标 + 巨潮定期报告公告",
        observed_at=observed_at,
        summary=(
            f"基本面区间 {fundamentals.get('requested_start_date')} 至 "
            f"{fundamentals.get('requested_end_date')}：区间内披露 {len(reports)} 份定期报告。"
        ),
        data=dict(fundamentals),
        limitations=limitations,
    )
