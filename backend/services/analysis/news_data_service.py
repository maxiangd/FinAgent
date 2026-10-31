"""个股新闻与公司公告，含历史区间查询。"""
from __future__ import annotations

import logging
import re
from datetime import date

import akshare as ak
import pandas as pd

from ..common.cache_manager import _cell_text, _retry, _to_iso_date, cached

logger = logging.getLogger("finagent.market.news")

@cached("news", 600, ttl_empty=60)
def _get_news(code: str) -> list[dict]:
    """获取最近的个股原始新闻。"""
    try:
        df = _retry(lambda: ak.stock_news_em(symbol=code), times=2)
        if df is None or df.empty:
            return []
        out = []
        for _, r in df.head(10).iterrows():
            title = str(r.get("新闻标题", "")).strip()
            if not title:
                continue
            out.append(
                {
                    "title": re.sub(r"\s+", " ", title),
                    "time": str(r.get("发布时间", ""))[:16],
                    "source": str(r.get("文章来源", "")),
                }
            )
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("%s 新闻获取失败: %s: %s", code, type(e).__name__, e)
        return []


@cached("news_history", 600, ttl_empty=60)
def _get_news_history_source(code: str) -> pd.DataFrame:
    """获取东方财富接口当前可返回的个股新闻列表。"""
    return _retry(lambda: ak.stock_news_em(symbol=code), times=2)


@cached("company_disclosures", 3600, ttl_empty=60)
def _get_company_disclosures(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """按公告日期获取区间内巨潮公司公告。"""
    return _retry(
        lambda: ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code,
            market="沪深京",
            category="",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        ),
        times=2,
    )


def get_historical_news(code: str, start_date: date, end_date: date) -> dict:
    """按发布时间整理区间新闻，并补充巨潮的区间公司公告。"""
    if start_date > end_date:
        raise ValueError("start_date 不能晚于 end_date")

    code = code.strip()
    requested_start = start_date.isoformat()
    requested_end = end_date.isoformat()
    items: list[dict] = []
    limitations: list[str] = []
    available_news_dates: list[str] = []

    try:
        df = _get_news_history_source(code)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                published_at = _to_iso_date(row.get("发布时间"))
                if not published_at:
                    continue
                available_news_dates.append(published_at)
                if not requested_start <= published_at <= requested_end:
                    continue
                title = _cell_text(row.get("新闻标题"))
                if not title:
                    continue
                items.append(
                    {
                        "kind": "news",
                        "title": re.sub(r"\s+", " ", title),
                        "published_at": published_at,
                        "source": _cell_text(row.get("文章来源")),
                        "url": _cell_text(row.get("新闻链接")) or None,
                    }
                )
    except Exception as e:  # noqa: BLE001
        logger.warning("%s 区间新闻获取失败: %s: %s", code, type(e).__name__, e)
        limitations.append(f"东方财富个股新闻获取失败：{type(e).__name__}。")

    media_coverage = {
        "available_start_date": min(available_news_dates) if available_news_dates else None,
        "available_end_date": max(available_news_dates) if available_news_dates else None,
        "returned_item_count": len(available_news_dates),
    }
    if not available_news_dates:
        limitations.append("东方财富接口没有返回可用于判断覆盖范围的新闻发布时间。")
    else:
        limitations.append(
            "东方财富接口仅提供最近一批个股新闻，按日期筛选后仍不能保证所选区间的新闻完整。"
        )
        if min(available_news_dates) > requested_start or max(available_news_dates) < requested_end:
            limitations.append(
                "东方财富当前返回结果的日期边界没有覆盖整个所选区间；区间新闻覆盖存在缺口。"
            )

    disclosure_coverage: dict = {
        "query_start_date": requested_start,
        "query_end_date": requested_end,
        "returned_item_count": 0,
    }
    try:
        df = _get_company_disclosures(code, requested_start, requested_end)
        if df is not None and not df.empty:
            disclosure_dates: list[str] = []
            for _, row in df.iterrows():
                published_at = _to_iso_date(row.get("公告时间"))
                if not published_at or not requested_start <= published_at <= requested_end:
                    continue
                title = _cell_text(row.get("公告标题"))
                if not title:
                    continue
                disclosure_dates.append(published_at)
                items.append(
                    {
                        "kind": "company_announcement",
                        "title": re.sub(r"\s+", " ", title),
                        "published_at": published_at,
                        "source": "巨潮资讯",
                        "url": _cell_text(row.get("公告链接")) or None,
                    }
                )
            disclosure_coverage["returned_item_count"] = len(disclosure_dates)
            disclosure_coverage["available_start_date"] = min(disclosure_dates) if disclosure_dates else None
            disclosure_coverage["available_end_date"] = max(disclosure_dates) if disclosure_dates else None
    except Exception as e:  # noqa: BLE001
        logger.warning("%s 区间公司公告获取失败: %s: %s", code, type(e).__name__, e)
        limitations.append(f"巨潮区间公司公告获取失败：{type(e).__name__}。")

    # 按日期倒序排列，让较新的事件优先展示和处理。
    items.sort(key=lambda item: item["published_at"], reverse=True)
    if not items:
        limitations.append("所选区间内没有获取到新闻或公司公告；不能据此断定期间没有相关事件。")

    return {
        "code": code,
        "requested_start_date": requested_start,
        "requested_end_date": requested_end,
        "items": items,
        "coverage": {
            "media_news": media_coverage,
            "company_announcements": disclosure_coverage,
        },
        "limitations": limitations,
    }
