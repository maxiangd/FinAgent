"""从行情服务构建 Agent 可用的初始分析上下文。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from agents.state import AgentState
from schemas.analysis import AnalysisStage, AnalysisTaskRequest, EvidenceItem
from services import market as market_service


_EVIDENCE_BAR_LIMIT = 60
_INDICATOR_WARMUP_BARS = 60


def build_initial_agent_state(request: AnalysisTaskRequest, task_id: str) -> AgentState:
    """按任务指定周期和日期区间取数、整理证据并初始化共享状态。

    指定日期区间或单一历史基准日期时，只使用相应时点可用的 K 线；
    当前快照、财务和新闻没有历史版本，因此不混入这类请求。
    """
    code = request.stock_code
    period = request.period
    is_range_request = request.start_date is not None
    is_point_in_time_request = request.analysis_date is not None

    if is_range_request:
        raw_kline = market_service.get_kline(
            code,
            period=period,
            start_date=request.start_date,
            end_date=request.end_date,
            warmup_bars=_INDICATOR_WARMUP_BARS,
        )
    else:
        raw_kline = market_service.get_kline(code, period=period)

    raw_dates = raw_kline.get("dates") or []
    raw_items = raw_kline.get("items") or []
    if not raw_dates or len(raw_dates) != len(raw_items):
        raise LookupError(f"{code} 没有可用的 {period} K 线数据")

    selected = list(zip(raw_dates, raw_items))
    if is_point_in_time_request:
        cutoff = request.analysis_date.isoformat()
        selected = [(bar_date, item) for bar_date, item in selected if bar_date <= cutoff]
    if not selected:
        cutoff = request.end_date or request.analysis_date
        raise LookupError(f"{code} 在所选区间截至 {cutoff} 没有可用的 {period} K 线数据")

    dates = [bar_date for bar_date, _ in selected]
    items = [item for _, item in selected]
    actual_start_date = date.fromisoformat(dates[0])
    actual_end_date = date.fromisoformat(dates[-1])
    warmup = (raw_kline.get("warmup") or []) if is_range_request else []
    kline_source = str(raw_kline.get("source") or "行情服务")
    requested_start_date = request.start_date
    requested_end_date = request.end_date or request.analysis_date

    kline_data: dict[str, Any] = {
        "code": code,
        "name": raw_kline.get("name"),
        "period": period,
        "source": kline_source,
        "requested_start_date": requested_start_date.isoformat() if requested_start_date else None,
        "requested_end_date": requested_end_date.isoformat() if requested_end_date else None,
        "actual_start_date": actual_start_date.isoformat(),
        "actual_end_date": actual_end_date.isoformat(),
        "dates": dates,
        "items": items,
        "warmup": warmup,
        "as_of": actual_end_date.isoformat(),
    }

    limitations = []
    if requested_start_date and actual_start_date > requested_start_date:
        limitations.append(
            f"请求开始日期为 {requested_start_date}，区间内首个可用交易日为 {actual_start_date}。"
        )
    if requested_end_date and actual_end_date < requested_end_date:
        limitations.append(
            f"请求结束日期为 {requested_end_date}，区间内最后可用交易日为 {actual_end_date}。"
        )
    if is_range_request or is_point_in_time_request:
        limitations.append(
            "现有接口没有对应历史时点的财务、新闻和实时行情版本；本次仅纳入所选周期的 K 线。"
        )
    if is_range_request and len(warmup) < _INDICATOR_WARMUP_BARS:
        limitations.append(
            f"区间开始前仅获取到 {len(warmup)} 根预热 K 线，部分技术指标可能缺少足够历史数据。"
        )

    recent_bars = [
        {"date": bar_date, **item}
        for bar_date, item in selected[-_EVIDENCE_BAR_LIMIT:]
    ]
    evidence = [
        EvidenceItem(
            category="market",
            source=kline_source,
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
            limitations=limitations.copy(),
        )
    ]

    market_snapshot: dict[str, Any] = {}
    if not is_range_request and not is_point_in_time_request:
        market_snapshot = market_service.get_snapshot(code)
        snapshot_meta = market_snapshot.get("meta") or {}
        snapshot_note = snapshot_meta.get("note")
        snapshot_limits = [
            "快照各字段没有独立的更新时间；记录时间表示本次读取时间。"
        ]
        if snapshot_note:
            snapshot_limits.append(f"数据源说明：{snapshot_note}")

        snapshot_data = {
            key: value
            for key, value in market_snapshot.items()
            if key not in {"news", "meta"}
        }
        evidence.append(
            EvidenceItem(
                category="market",
                source="AKShare 行情与基本面快照",
                observed_at=datetime.now(timezone.utc),
                summary=f"{market_snapshot.get('name') or code} 当前行情与基本面快照。",
                data=snapshot_data,
                limitations=snapshot_limits,
            )
        )

        news = market_snapshot.get("news") or []
        if news:
            evidence.append(
                EvidenceItem(
                    category="news",
                    source="东方财富个股新闻（AKShare）",
                    observed_at=datetime.now(timezone.utc),
                    summary=f"获取到 {len(news)} 条近期个股新闻。",
                    data={"news": news},
                    limitations=["新闻条目时间以数据源返回值为准。"],
                )
            )

    return AgentState(
        messages=[],
        task_id=task_id,
        stock_code=code,
        analysis_period=period,
        analysis_date=actual_end_date,
        requested_analysis_date=request.analysis_date,
        requested_start_date=requested_start_date,
        requested_end_date=requested_end_date,
        actual_start_date=actual_start_date,
        actual_end_date=actual_end_date,
        sender="data_ingestion",
        current_stage=AnalysisStage.INGEST,
        market_snapshot=market_snapshot,
        kline_data=kline_data,
        evidence=evidence,
        investment_debate_state={
            "bull_history": [],
            "bear_history": [],
            "history": [],
            "current_speaker": "bull",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        },
        risk_debate_state={
            "aggressive_history": [],
            "neutral_history": [],
            "conservative_history": [],
            "history": [],
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        },
        tool_call_counts={"market": 0, "fundamental": 0, "news": 0},
        errors=[],
    )
