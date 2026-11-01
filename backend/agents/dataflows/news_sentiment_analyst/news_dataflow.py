"""整理当前或历史区间新闻，并生成带来源和覆盖说明的证据。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

from app.schemas.analysis_schemas import EvidenceItem
from data_sources.analysis.news_data_service import get_historical_news


def extract_news(snapshot: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """提取数据源返回的个股近期新闻。"""
    if not snapshot:
        return []
    return [item for item in (snapshot.get("news") or []) if isinstance(item, dict)]


def build_current_news_data(news: list[dict[str, Any]]) -> dict[str, Any]:
    """把当前新闻整理成带覆盖说明的统一结构。"""
    return {
        "items": news,
        "requested_start_date": None,
        "requested_end_date": None,
        "coverage": {"media_news": {"returned_item_count": len(news)}},
        "limitations": ["当前新闻接口仅返回最近一批新闻，未提供完整历史覆盖范围。"],
    }


def fetch_historical_news(
    code: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """按用户选择的日期范围读取个股新闻和巨潮公司公告。"""
    return get_historical_news(code, start_date, end_date)


def build_news_evidence(
    news: Mapping[str, Any] | list[dict[str, Any]],
    observed_at: datetime,
) -> EvidenceItem | None:
    """为新闻和公司公告建立独立证据，并保留各自发布时间。"""
    news_data = dict(news) if isinstance(news, Mapping) else {"items": news}
    items = news_data.get("items") or []
    if not items and not news_data.get("limitations"):
        return None
    limitations = list(news_data.get("limitations") or [])
    if not limitations:
        limitations = ["新闻条目时间以数据源返回值为准。"]
    return EvidenceItem(
        category="news",
        source="东方财富个股新闻与巨潮公司公告（AKShare）",
        observed_at=observed_at,
        summary=f"整理到 {len(items)} 条新闻或公司公告。",
        data=news_data,
        limitations=limitations,
    )
