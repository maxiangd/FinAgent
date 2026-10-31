"""只读取当前分析任务 K 线范围的行情工具。"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Callable, Mapping

from schemas.analysis import EvidenceItem


MAX_TOOL_BARS = 120


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rounded(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _window_statistics(kline: Mapping[str, Any]) -> dict[str, Any]:
    dates = list(kline.get("dates") or [])
    bars = list(kline.get("items") or [])
    if not dates or len(dates) != len(bars):
        raise ValueError("当前任务没有可计算的 K 线区间")

    rows = [(bar_date, bar) for bar_date, bar in zip(dates, bars)]
    valid_closes = [
        (bar_date, _number(bar.get("close")))
        for bar_date, bar in rows
        if _number(bar.get("close")) is not None
    ]
    if not valid_closes:
        raise ValueError("所选区间没有有效收盘价")

    first_date, first_close = valid_closes[0]
    last_date, last_close = valid_closes[-1]
    assert first_close is not None and last_close is not None
    close_values = [value for _, value in valid_closes if value is not None]
    window_mean = sum(close_values) / len(close_values)

    high_candidates = [
        (bar_date, _number(bar.get("high")) or _number(bar.get("close")))
        for bar_date, bar in rows
    ]
    low_candidates = [
        (bar_date, _number(bar.get("low")) or _number(bar.get("close")))
        for bar_date, bar in rows
    ]
    high_date, highest = max(
        ((d, v) for d, v in high_candidates if v is not None),
        key=lambda item: item[1],
    )
    low_date, lowest = min(
        ((d, v) for d, v in low_candidates if v is not None),
        key=lambda item: item[1],
    )

    peak_date, peak_close = valid_closes[0]
    worst_drawdown = 0.0
    drawdown_peak_date = peak_date
    drawdown_trough_date = peak_date
    for bar_date, close in valid_closes:
        assert close is not None
        if close > peak_close:
            peak_date, peak_close = bar_date, close
        drawdown = (close / peak_close - 1) * 100 if peak_close else 0.0
        if drawdown < worst_drawdown:
            worst_drawdown = drawdown
            drawdown_peak_date = peak_date
            drawdown_trough_date = bar_date

    warmup = list(kline.get("warmup") or [])
    indicator_closes = [
        value
        for value in (
            _number(bar.get("close"))
            for bar in warmup + bars
        )
        if value is not None
    ]
    moving_averages = {}
    for period in (5, 10, 20, 60):
        moving_averages[f"MA{period}"] = (
            _rounded(sum(indicator_closes[-period:]) / period)
            if len(indicator_closes) >= period
            else None
        )

    return {
        "period": kline.get("period"),
        "source": kline.get("source"),
        "start_date": dates[0],
        "end_date": dates[-1],
        "bar_count": len(bars),
        "warmup_bar_count": len(warmup),
        "first_close_date": first_date,
        "first_close": _rounded(first_close),
        "last_close_date": last_date,
        "last_close": _rounded(last_close),
        "window_change_pct": _rounded((last_close / first_close - 1) * 100) if first_close else None,
        "highest_price": _rounded(highest),
        "highest_price_date": high_date,
        "lowest_price": _rounded(lowest),
        "lowest_price_date": low_date,
        "window_average_close": _rounded(window_mean),
        "last_close_vs_window_average_pct": _rounded((last_close / window_mean - 1) * 100) if window_mean else None,
        "maximum_close_drawdown_pct": _rounded(worst_drawdown),
        "drawdown_peak_date": drawdown_peak_date,
        "drawdown_trough_date": drawdown_trough_date,
        "latest_moving_averages": moving_averages,
        "calculation_notes": [
            "区间涨幅按区间首根与末根 K 线的收盘价计算。",
            "最大收盘回撤按所选区间内此前最高收盘价至后续最低收盘价计算。",
            "移动平均线可使用区间外预热 K 线；窗口统计只使用所选区间 K 线。",
        ],
    }


def build_market_tools(
    context: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Callable[[str, dict[str, Any]], dict[str, Any]], list[EvidenceItem]]:
    """为单次任务创建工具；工具不能访问股票或日期范围以外的数据。"""
    kline = context.get("kline_data") or {}
    dates = list(kline.get("dates") or [])
    bars = list(kline.get("items") or [])
    if not dates or len(dates) != len(bars):
        raise ValueError("行情分析需要有效的 K 线数据")

    market_evidence = next(
        (
            evidence
            for evidence in context.get("evidence", [])
            if getattr(evidence, "category", None) == "market"
        ),
        None,
    )
    if market_evidence is None:
        raise ValueError("分析上下文缺少 K 线来源证据")

    stats = _window_statistics(kline)
    technical_evidence = EvidenceItem(
        category="technical",
        source=f"{kline.get('source') or '行情服务'} K 线区间计算",
        observed_at=context.get("actual_end_date"),
        summary=(
            f"{kline.get('period')} 区间 {stats['start_date']} 至 {stats['end_date']}："
            f"{stats['bar_count']} 根 K 线，区间涨幅 {stats['window_change_pct']}%。"
        ),
        data=stats,
        limitations=list(market_evidence.limitations),
    )
    evidence = [market_evidence, technical_evidence]

    tool_schemas = [
        {
            "type": "function",
            "function": {
                "name": "get_window_statistics",
                "description": "读取当前任务所选 K 线区间的涨幅、高低点、均值、收盘最大回撤和最新均线。统计范围固定为用户选择的日期。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_kline_bars",
                "description": "读取当前任务所选日期范围内的 K 线细节。可以选日期子区间，最多返回 120 根；不能读取区间外或预热 K 线。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string", "description": "可选，YYYY-MM-DD，不能早于所选区间"},
                        "end_date": {"type": "string", "description": "可选，YYYY-MM-DD，不能晚于所选区间"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": MAX_TOOL_BARS},
                    },
                    "additionalProperties": False,
                },
            },
        },
    ]

    def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "get_window_statistics":
            return {
                "statistics": stats,
                "evidence_ids": [technical_evidence.evidence_id, market_evidence.evidence_id],
            }
        if name == "get_kline_bars":
            start_text = arguments.get("start_date") or dates[0]
            end_text = arguments.get("end_date") or dates[-1]
            try:
                requested_start = date.fromisoformat(start_text)
                requested_end = date.fromisoformat(end_text)
                actual_start = date.fromisoformat(dates[0])
                actual_end = date.fromisoformat(dates[-1])
            except (TypeError, ValueError) as exc:
                raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc
            if requested_start > requested_end:
                raise ValueError("起始日期不能晚于结束日期")
            if requested_start < actual_start or requested_end > actual_end:
                raise ValueError("工具只能读取当前任务选定区间内的 K 线")
            try:
                limit = int(arguments.get("limit", 60))
            except (TypeError, ValueError) as exc:
                raise ValueError("limit 必须是整数") from exc
            if not 1 <= limit <= MAX_TOOL_BARS:
                raise ValueError(f"limit 必须在 1 到 {MAX_TOOL_BARS} 之间")

            selected = [
                {"date": bar_date, **bar}
                for bar_date, bar in zip(dates, bars)
                if start_text <= bar_date <= end_text
            ]
            return {
                "requested_range": {"start_date": start_text, "end_date": end_text},
                "returned_bar_count": min(len(selected), limit),
                "bars": selected[-limit:],
                "evidence_ids": [market_evidence.evidence_id],
            }
        raise ValueError(f"未开放此工具：{name}")

    return tool_schemas, execute, evidence
