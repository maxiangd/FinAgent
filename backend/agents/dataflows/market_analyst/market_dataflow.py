"""获取并整理市场行情与 K 线证据。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

from app.schemas.analysis_schemas import EvidenceItem
from data_sources.market.kline_data_service import get_kline
from data_sources.market.market_snapshot_service import get_snapshot


EVIDENCE_BAR_LIMIT = 60
INDICATOR_WARMUP_BARS = 60

_MARKET_SNAPSHOT_FIELDS = (
    "code",
    "name",
    "price",
    "changePct",
    "volRatio",
    "turnover",
)


def fetch_kline_data(
    code: str,
    period: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    """按分析周期和日期范围读取 K 线；区间任务额外读取指标预热数据。"""
    if start_date is not None and end_date is not None:
        return get_kline(
            code,
            period=period,
            start_date=start_date,
            end_date=end_date,
            warmup_bars=INDICATOR_WARMUP_BARS,
        )
    return get_kline(code, period=period)


def fetch_current_snapshot(code: str) -> dict[str, Any]:
    """读取供当前时点分析使用的行情、基本面和近期新闻快照。"""
    return get_snapshot(code)


def prepare_kline_context(
    raw_kline: Mapping[str, Any],
    code: str,
    period: str,
    requested_start_date: date | None = None,
    requested_end_date: date | None = None,
    analysis_date: date | None = None,
) -> tuple[dict[str, Any], EvidenceItem, date, date]:
    """校验 K 线、应用单日基准过滤并生成 K 线数据与证据。"""
    raw_dates = raw_kline.get("dates") or []
    raw_items = raw_kline.get("items") or []
    if not raw_dates or len(raw_dates) != len(raw_items):
        raise LookupError(f"{code} 没有可用的 {period} K 线数据")

    selected = list(zip(raw_dates, raw_items))
    if analysis_date is not None:
        cutoff = analysis_date.isoformat()
        selected = [(bar_date, item) for bar_date, item in selected if bar_date <= cutoff]
    if not selected:
        cutoff = requested_end_date or analysis_date
        raise LookupError(f"{code} 在所选区间截至 {cutoff} 没有可用的 {period} K 线数据")

    dates = [bar_date for bar_date, _ in selected]
    items = [item for _, item in selected]
    actual_start_date = date.fromisoformat(dates[0])
    actual_end_date = date.fromisoformat(dates[-1])
    is_range_request = requested_start_date is not None
    warmup = (raw_kline.get("warmup") or []) if is_range_request else []
    source = str(raw_kline.get("source") or "行情服务")

    limitations: list[str] = []
    if requested_start_date and actual_start_date > requested_start_date:
        limitations.append(
            f"请求开始日期为 {requested_start_date}，区间内首个可用交易日为 {actual_start_date}。"
        )
    if requested_end_date and actual_end_date < requested_end_date:
        limitations.append(
            f"请求结束日期为 {requested_end_date}，区间内最后可用交易日为 {actual_end_date}。"
        )
    if requested_start_date or analysis_date:
        limitations.append(
            "历史基本面和新闻由各自数据流按披露日、发布时间获取；PE、市值、量比等实时行情快照没有历史版本。"
        )
    if is_range_request and len(warmup) < INDICATOR_WARMUP_BARS:
        limitations.append(
            f"区间开始前仅获取到 {len(warmup)} 根预热 K 线，部分技术指标可能缺少足够历史数据。"
        )

    kline_data: dict[str, Any] = {
        "code": code,
        "name": raw_kline.get("name"),
        "period": period,
        "source": source,
        "requested_start_date": requested_start_date.isoformat() if requested_start_date else None,
        "requested_end_date": requested_end_date.isoformat() if requested_end_date else None,
        "actual_start_date": actual_start_date.isoformat(),
        "actual_end_date": actual_end_date.isoformat(),
        "dates": dates,
        "items": items,
        "warmup": warmup,
        "as_of": actual_end_date.isoformat(),
    }
    recent_bars = [
        {"date": bar_date, **item}
        for bar_date, item in selected[-EVIDENCE_BAR_LIMIT:]
    ]
    evidence = EvidenceItem(
        category="market",
        source=source,
        observed_at=actual_end_date,
        summary=(
            f"{code} {period} K 线：{actual_start_date} 至 {actual_end_date}，"
            f"共 {len(items)} 根。"
        ),
        data={
            "period": period,
            "requested_start_date": requested_start_date.isoformat() if requested_start_date else None,
            "requested_end_date": requested_end_date.isoformat() if requested_end_date else None,
            "actual_start_date": actual_start_date.isoformat(),
            "actual_end_date": actual_end_date.isoformat(),
            "bar_count": len(items),
            "recent_bars": recent_bars,
            "warmup_bars": warmup,
        },
        limitations=limitations,
    )
    return kline_data, evidence, actual_start_date, actual_end_date


def extract_market_snapshot(snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """从当前快照中提取行情字段，基本面和新闻由各自数据流处理。"""
    if not snapshot:
        return {}
    return {key: snapshot[key] for key in _MARKET_SNAPSHOT_FIELDS if key in snapshot}


def build_market_snapshot_evidence(
    market_data: Mapping[str, Any],
    observed_at: datetime,
    source_note: str | None = None,
) -> EvidenceItem | None:
    """为当前行情快照建立来源和时间明确的证据。"""
    if not market_data:
        return None
    limitations = ["快照字段没有独立更新时间；记录时间表示本次读取时间。"]
    if source_note:
        limitations.append(f"数据源说明：{source_note}")
    return EvidenceItem(
        category="market",
        source="行情快照（AKShare 多数据源）",
        observed_at=observed_at,
        summary=f"{market_data.get('name') or market_data.get('code')} 当前行情快照。",
        data=dict(market_data),
        limitations=limitations,
    )
