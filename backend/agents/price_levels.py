"""模型未给出有效价位时，按近期 K 线估算目标价与止损价。"""

from __future__ import annotations

from typing import Any, Mapping

# 用最近约一个月的 K 线取支撑/阻力，避免用整个分析窗口的极值导致止损过远
RECENT_BARS = 20
ATR_BARS = 14


def _recent_bars(context: Mapping[str, Any], count: int) -> list[dict[str, Any]]:
    items = (context or {}).get("kline_data", {}).get("items") or []
    return items[-count:]


def _average_true_range(context: Mapping[str, Any]) -> float | None:
    """14 根 K 线的平均真实波幅，用来在近期区间内没有可用价位时给出缓冲。"""
    bars = _recent_bars(context, ATR_BARS + 1)
    ranges: list[float] = []
    previous_close: float | None = None
    for bar in bars:
        high, low, close = bar.get("high"), bar.get("low"), bar.get("close")
        if high is None or low is None or close is None:
            continue
        high, low, close = float(high), float(low), float(close)
        if previous_close is None:
            ranges.append(high - low)
        else:
            ranges.append(
                max(high - low, abs(high - previous_close), abs(low - previous_close))
            )
        previous_close = close
    return sum(ranges) / len(ranges) if ranges else None


def target_and_stop(
    context: Mapping[str, Any] | None, bullish: bool
) -> tuple[float | None, float | None]:
    """返回 (target, stop)：看多时目标取近期阻力、止损取近期支撑，看空时相反。

    近期区间内没有合适的价位时，用最新收盘价 ± 2×ATR 兜底；没有行情数据时返回空。
    """
    bars = _recent_bars(context or {}, RECENT_BARS)
    closes = [float(bar["close"]) for bar in bars if bar.get("close") is not None]
    highs = [float(bar["high"]) for bar in bars if bar.get("high") is not None]
    lows = [float(bar["low"]) for bar in bars if bar.get("low") is not None]
    if not closes:
        return None, None

    close = closes[-1]
    resistance = max(highs) if highs else None
    support = min(lows) if lows else None
    atr = _average_true_range(context or {})
    buffer = 2 * atr if atr else close * 0.05

    def above(level: float | None) -> float:
        return round(level, 2) if level is not None and level > close else round(close + buffer, 2)

    def below(level: float | None) -> float:
        return round(level, 2) if level is not None and level < close else round(close - buffer, 2)

    if bullish:
        return above(resistance), below(support)
    return below(support), above(resistance)
