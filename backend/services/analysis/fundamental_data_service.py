"""财务指标、历史基本面与财报公告。"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

import akshare as ak
import pandas as pd

from ..common.cache_manager import _cell_text, _fcol, _num, _retry, _to_iso_date, cached

logger = logging.getLogger("finagent.market.financials")

# ---------- 财务指标（新浪财务分析指标） ----------
@cached("financial", 3600, ttl_empty=60)
def _get_financial(code: str) -> dict:
    """获取并整理 ROE、利润率和收入/净利润增长率。"""
    try:
        df = _retry(lambda: ak.stock_financial_analysis_indicator(symbol=code))
        if df is None or df.empty:
            return {}
        roe = _fcol(df, "净资产收益率")
        # 优先使用销售毛利率；缺失时再使用主营业务利润率。
        margin = _fcol(df, "销售毛利率")
        if margin is None:
            margin = _fcol(df, "主营业务利润率")
        return {
            "roe": _num(roe),
            "revGrowth": _num(_fcol(df, "主营业务收入增长率")),
            "profitGrowth": _num(_fcol(df, "净利润增长率")),
            "margin": _num(margin),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("%s 财务指标获取失败: %s: %s", code, type(e).__name__, e)
        return {}


@cached("financial_history", 86400, ttl_empty=60)
def _get_financial_history(code: str, start_year: str) -> pd.DataFrame:
    """获取所需起始年份以来的新浪历史财务指标。"""
    return _retry(
        lambda: ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year),
        times=2,
    )


@cached("financial_disclosures", 86400, ttl_empty=60)
def _get_financial_disclosures(
    code: str,
    category: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """按公告日期获取巨潮的定期报告披露记录。"""
    return _retry(
        lambda: ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code,
            market="沪深京",
            category=category,
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        ),
        times=2,
    )


def _financial_report_period(title: str, category: str) -> str | None:
    """根据公告标题和报告类别识别财报所属期。"""
    match = re.search(r"(20\d{2})年", title)
    if not match:
        match = re.search(r"(20\d{2})", title)
    if not match:
        return None
    year = match.group(1)
    month_day = {
        "一季报": "03-31",
        "半年报": "06-30",
        "三季报": "09-30",
        "年报": "12-31",
    }.get(category)
    return f"{year}-{month_day}" if month_day else None


def get_historical_fundamentals(
    code: str,
    start_date: date,
    end_date: date,
) -> dict:
    """按实际披露日整理区间开始时已知及区间内新披露的财务指标。"""
    if start_date > end_date:
        raise ValueError("start_date 不能晚于 end_date")

    code = code.strip()
    requested_start = start_date.isoformat()
    requested_end = end_date.isoformat()
    disclosure_start = (start_date - timedelta(days=1095)).isoformat()
    history_start_year = str(max(2000, start_date.year - 3))
    limitations = [
        "新浪历史财务指标按报告期提供；本结果使用巨潮公告日期判断该报告何时公开。",
        "历史财务指标可能包含后续更正值，数据源不保留每次公告时的完整版本。",
        "历史 PE、市值和股息率尚未接入历史序列，本结果不包含这些历史估值。",
    ]

    try:
        df = _get_financial_history(code, history_start_year)
    except Exception as e:  # noqa: BLE001
        logger.warning("%s 历史财务指标获取失败: %s: %s", code, type(e).__name__, e)
        return {
            "code": code,
            "requested_start_date": requested_start,
            "requested_end_date": requested_end,
            "baseline": None,
            "reports_in_range": [],
            "limitations": [*limitations, f"历史财务指标获取失败：{type(e).__name__}。"],
        }

    if df is None or df.empty:
        return {
            "code": code,
            "requested_start_date": requested_start,
            "requested_end_date": requested_end,
            "baseline": None,
            "reports_in_range": [],
            "limitations": [*limitations, "数据源没有返回历史财务指标。"],
        }

    report_date_col = next(
        (column for column in df.columns if str(column).strip() in ("日期", "报告日期", "报告期")),
        None,
    )
    if report_date_col is None:
        return {
            "code": code,
            "requested_start_date": requested_start,
            "requested_end_date": requested_end,
            "baseline": None,
            "reports_in_range": [],
            "limitations": [*limitations, "历史财务数据缺少报告期字段，无法与公告对应。"],
        }

    financial_by_period: dict[str, dict] = {}
    for _, row in df.iterrows():
        report_date = _to_iso_date(row.get(report_date_col))
        if not report_date:
            continue
        margin = next(
            (row[column] for column in df.columns if "销售毛利率" in str(column) and pd.notna(row[column])),
            None,
        )
        if margin is None:
            margin = next(
                (row[column] for column in df.columns if "主营业务利润率" in str(column) and pd.notna(row[column])),
                None,
            )
        metrics = {
            "report_date": report_date,
            "roe": None,
            "revGrowth": None,
            "profitGrowth": None,
            "margin": _num(margin),
        }
        for field, key in (
            ("roe", "净资产收益率"),
            ("revGrowth", "主营业务收入增长率"),
            ("profitGrowth", "净利润增长率"),
        ):
            value = next(
                (row[column] for column in df.columns if key in str(column) and pd.notna(row[column])),
                None,
            )
            metrics[field] = _num(value)
        financial_by_period[report_date] = metrics

    disclosures: dict[str, dict] = {}
    for category in ("一季报", "半年报", "三季报", "年报"):
        try:
            reports = _get_financial_disclosures(
                code,
                category,
                disclosure_start,
                requested_end,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("%s %s公告日期获取失败: %s: %s", code, category, type(e).__name__, e)
            limitations.append(f"{category}公告日期获取失败，相关报告可能未纳入。")
            continue
        if reports is None or reports.empty:
            continue
        for _, row in reports.iterrows():
            title = _cell_text(row.get("公告标题"))
            report_period = _financial_report_period(title, category)
            published_at = _to_iso_date(row.get("公告时间"))
            if not report_period or not published_at or report_period not in financial_by_period:
                continue
            record = {
                **financial_by_period[report_period],
                "publication_date": published_at,
                "title": title,
                "source": "新浪历史财务指标 + 巨潮公告日期",
            }
            previous = disclosures.get(report_period)
            if previous is None or published_at < previous["publication_date"]:
                disclosures[report_period] = record

    dated_reports = sorted(
        disclosures.values(),
        key=lambda report: (report["publication_date"], report["report_date"]),
    )
    baseline_candidates = [
        report for report in dated_reports if report["publication_date"] < requested_start
    ]
    baseline = baseline_candidates[-1] if baseline_candidates else None
    reports_in_range = [
        report
        for report in dated_reports
        if requested_start <= report["publication_date"] <= requested_end
    ]
    if baseline is None:
        limitations.append("未找到区间开始日之前已披露且能匹配到财务指标的定期报告。")
    if not reports_in_range:
        limitations.append("区间内没有匹配到定期报告披露；这不代表区间内没有其他公司公告。")

    return {
        "code": code,
        "requested_start_date": requested_start,
        "requested_end_date": requested_end,
        "baseline": baseline,
        "reports_in_range": reports_in_range,
        "coverage": {
            "financial_history_start_year": history_start_year,
            "disclosure_query_start": disclosure_start,
            "disclosure_query_end": requested_end,
            "matched_report_count": len(dated_reports),
        },
        "limitations": limitations,
    }
