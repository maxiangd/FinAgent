"""K 线数据：日线新浪→腾讯→东财，周/月线雪球→腾讯。"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from math import ceil

import akshare as ak
import pandas as pd
import requests

from config.settings import get_env_int

from ..common.cache_manager import _num, _retry, cached
from .stock_name_service import get_name

logger = logging.getLogger("finagent.market.kline")

KLINE_LIMITS = {
    "daily": get_env_int("KLINE_DAILY_LIMIT", 520, minimum=1, maximum=5000),
    "weekly": get_env_int("KLINE_WEEKLY_LIMIT", 260, minimum=1, maximum=5000),
    "monthly": get_env_int("KLINE_MONTHLY_LIMIT", 120, minimum=1, maximum=5000),
}


# ---------- K线（日线：新浪 → 腾讯 → 东财；周线/月线：雪球 → 腾讯） ----------
_SINA_COLS = {"date": "date", "open": "open", "close": "close", "high": "high", "low": "low", "volume": "volume"}
_EM_COLS = {"date": "日期", "open": "开盘", "close": "收盘", "high": "最高", "low": "最低", "volume": "成交量"}

_CST = timezone(timedelta(hours=8))
_XQ_KLINE_URL = "https://stock.xueqiu.com/v5/stock/chart/kline.json"
_XQ_LOCK = threading.Lock()
_xq_session: requests.Session | None = None


def _xq_client() -> requests.Session:
    """雪球接口需要登录态 cookie，首次调用时从首页换取并复用。"""
    global _xq_session
    with _XQ_LOCK:
        if _xq_session is None:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Referer": "https://xueqiu.com/",
            })
            session.get("https://xueqiu.com/", timeout=10)
            _xq_session = session
        return _xq_session


def _xq_reset() -> None:
    """cookie 失效时丢弃连接，下次调用重新换票。"""
    global _xq_session
    with _XQ_LOCK:
        _xq_session = None


def _xq_symbol(code: str, prefix: str) -> str:
    return ("SH" if prefix == "sh" else "SZ" if prefix == "sz" else "BJ") + code


def _fetch_xq_kline(
    code: str,
    prefix: str,
    period: str,
    limit: int,
    end_date: date | None = None,
) -> pd.DataFrame:
    """雪球周/月线，type=before 为前复权（乘性，与新浪日线口径一致）。"""
    end_datetime = datetime.combine(end_date, datetime_time.max, tzinfo=_CST) if end_date else None
    params = {
        "symbol": _xq_symbol(code, prefix),
        "begin": int((end_datetime.timestamp() if end_datetime else time.time()) * 1000),
        # 雪球周期取 week/month，与内部 weekly/monthly 命名不同
        "period": "week" if period == "weekly" else "month",
        "type": "before",
        "count": -limit,
        "indicator": "kline",
    }
    resp = _xq_client().get(_XQ_KLINE_URL, params=params, timeout=10)
    if resp.status_code in (400, 401):
        _xq_reset()
        resp = _xq_client().get(_XQ_KLINE_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    items, cols = data.get("item") or [], data.get("column") or []
    if not items:
        raise LookupError("empty response")
    idx = {c: i for i, c in enumerate(cols)}
    return pd.DataFrame([
        {
            "date": pd.Timestamp(it[idx["timestamp"]], unit="ms", tz=_CST).strftime("%Y-%m-%d"),
            "open": it[idx["open"]],
            "close": it[idx["close"]],
            "high": it[idx["high"]],
            "low": it[idx["low"]],
            "volume": it[idx["volume"]],
        }
        for it in items
    ])


def _fetch_tx_kline(symbol: str, period: str, start: str, end: str, limit: int) -> pd.DataFrame:
    """腾讯周/月线兜底。返回行格式：[日期, 开, 收, 高, 低, 成交量(手), ...]。"""
    tx_period = "week" if period == "weekly" else "month"
    params = {
        "_var": f"kline_{tx_period}qfq",
        # 腾讯要求日期带横线，传 20200201 这种格式会返回 param error
        "param": f"{symbol},{tx_period},{start[:4]}-{start[4:6]}-{start[6:]},{end[:4]}-{end[4:6]}-{end[6:]},{min(max(limit, 1), 2000)},qfq",
        "r": "0.82",
    }
    resp = requests.get(
        "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.text.split("=", 1)[1] if "=" in resp.text else resp.text
    node = (json.loads(body).get("data") or {}).get(symbol) or {}
    rows = node.get(f"qfq{tx_period}") or node.get(tx_period) or []
    if not rows:
        raise LookupError("empty response")
    return pd.DataFrame([
        {
            "date": str(r[0])[:10],
            "open": r[1],
            "close": r[2],
            "high": r[3],
            "low": r[4],
            # 腾讯成交量单位为手，统一换算成股，与新浪/雪球一致
            "volume": float(r[5]) * 100 if str(r[5]).lower() not in ("nan", "none", "") else 0,
        }
        for r in rows[-limit:]
    ])


def _parse_kline_date(value, field_name: str) -> date | None:
    """把日期参数统一转成 date；格式错误时给出清晰提示。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} 必须使用 YYYY-MM-DD 格式") from exc


def _fetch_kline_frame(
    code: str,
    period: str,
    fetch_start: date,
    fetch_end: date,
    fetch_limit: int,
) -> tuple[pd.DataFrame, str]:
    """从可用数据源取 K 线，返回规范列（date/open/close/high/low/volume）与来源名。"""
    s = fetch_start.strftime("%Y%m%d")
    e = fetch_end.strftime("%Y%m%d")

    if code.startswith(("6", "9")):
        prefix = "sh"
    elif code.startswith(("0", "2", "3")):
        prefix = "sz"
    else:
        prefix = "bj"
    symbol = prefix + code

    if period == "daily":
        sources = [
            ("新浪", lambda: ak.stock_zh_a_daily(symbol=symbol, start_date=s, end_date=e, adjust="qfq"), _SINA_COLS),
            ("腾讯", lambda: ak.stock_zh_a_hist_tx(symbol=symbol, start_date=s, end_date=e, adjust="qfq"), _SINA_COLS),
            ("东财", lambda: ak.stock_zh_a_hist(symbol=code, period="daily", start_date=s, end_date=e, adjust="qfq"), _EM_COLS),
        ]
    else:
        # 东财行情接口在部分网络下直接断连，周/月线改走雪球（真实周期K线，非日线聚合）
        sources = [
            ("雪球", lambda: _fetch_xq_kline(code, prefix, period, fetch_limit, fetch_end), _SINA_COLS),
            ("腾讯", lambda: _fetch_tx_kline(symbol, period, s, e, fetch_limit), _SINA_COLS),
        ]

    errors: list[str] = []

    def try_sources(candidates):
        for name, fetch, colmap in candidates:
            try:
                result = _retry(fetch, delay=0.8)
                if result is None or result.empty:
                    raise LookupError("empty response")
                return result, colmap, name
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                logger.warning("%s %s K线失败（%s）", code, name, f"{type(exc).__name__}: {exc}")
        return None, None, None

    df, cols, source = try_sources(sources)
    if df is None or df.empty:
        raise LookupError(f"{code} 未获取到 K 线数据 | " + " | ".join(errors))

    frame = pd.DataFrame({
        "date": pd.to_datetime(df[cols["date"]], errors="coerce").dt.strftime("%Y-%m-%d"),
        "open": pd.to_numeric(df[cols["open"]], errors="coerce"),
        "close": pd.to_numeric(df[cols["close"]], errors="coerce"),
        "high": pd.to_numeric(df[cols["high"]], errors="coerce"),
        "low": pd.to_numeric(df[cols["low"]], errors="coerce"),
        "volume": pd.to_numeric(df[cols["volume"]], errors="coerce"),
    })
    frame = frame[frame["date"].notna()].sort_values("date").reset_index(drop=True)
    if frame.empty:
        raise LookupError(f"{code} 的 K 线日期无法解析")
    return frame, source


def _row_to_item(row) -> dict:
    return {
        "open": _num(row["open"]),
        "close": _num(row["close"]),
        "high": _num(row["high"]),
        "low": _num(row["low"]),
        "volume": _num(row["volume"], 0),
    }


@cached("kline_series", 300)
def _default_series(code: str, period: str) -> dict:
    """按该周期的默认根数取一次完整序列；图表展示与后续分析共用同一份缓存。"""
    configured_limit = KLINE_LIMITS[period]
    days_per_bar = {"daily": 2.2, "weekly": 8.5, "monthly": 37}[period]
    fetch_end = date.today()
    lookback_days = max(1100 if period == "daily" else 0, int(configured_limit * days_per_bar) + 45)
    fetch_start = fetch_end - timedelta(days=lookback_days)
    frame, source = _fetch_kline_frame(code, period, fetch_start, fetch_end, configured_limit)
    frame = frame.tail(configured_limit)
    return {
        "source": source,
        "dates": frame["date"].tolist(),
        "items": [_row_to_item(row) for _, row in frame.iterrows()],
    }


def get_kline(
    code: str,
    limit=None,
    period: str = "daily",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    warmup_bars: int = 0,
):
    """获取指定周期 K 线；区间请求优先从已缓存的完整序列本地切片。"""
    period = str(period).lower()
    if period not in KLINE_LIMITS:
        raise ValueError("period must be daily, weekly, or monthly")
    start_date = _parse_kline_date(start_date, "start_date")
    end_date = _parse_kline_date(end_date, "end_date")
    if (start_date is None) != (end_date is None):
        raise ValueError("start_date 和 end_date 必须同时提供")
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date 不能晚于 end_date")
    if end_date and end_date > date.today():
        raise ValueError("end_date 不能晚于今天")
    try:
        warmup_bars = int(warmup_bars)
    except (TypeError, ValueError) as exc:
        raise ValueError("warmup_bars 必须是整数") from exc
    if not 0 <= warmup_bars <= 200:
        raise ValueError("warmup_bars 必须在 0 到 200 之间")
    if warmup_bars and start_date is None:
        raise ValueError("只有指定日期范围时才能请求预热 K 线")

    configured_limit = KLINE_LIMITS[period] if limit is None else min(max(int(limit), 1), 5000)
    code = code.strip()
    days_per_bar = {"daily": 2.2, "weekly": 8.5, "monthly": 37}[period]

    if start_date is None:
        series = _default_series(code, period)
        dates = series["dates"][-configured_limit:]
        items = series["items"][-configured_limit:]
        if not dates:
            raise LookupError(f"{code} 未获取到 {period} K 线数据")
        return {
            "code": code,
            "name": get_name(code),
            "period": period,
            "limit": configured_limit,
            "source": series["source"],
            "requested_start_date": None,
            "requested_end_date": None,
            "actual_start_date": dates[0],
            "actual_end_date": dates[-1],
            "dates": dates,
            "items": items,
            "warmup": [],
        }

    # 区间请求：先算出回源窗口，缓存窗口不够时用它重新取数
    fetch_start = start_date - timedelta(days=int(warmup_bars * days_per_bar) + 10)
    fetch_end = end_date
    calendar_days_per_bar = {"daily": 1.5, "weekly": 7.5, "monthly": 31}[period]
    required_limit = ceil((fetch_end - fetch_start).days / calendar_days_per_bar) + 20
    if required_limit > 5000:
        raise ValueError("日期范围过长，请缩短区间后重试")
    fetch_limit = min(required_limit, configured_limit) if limit is not None else required_limit

    start_text = start_date.isoformat()
    end_text = end_date.isoformat()
    series = _default_series(code, period)

    if series["dates"] and series["dates"][0] <= fetch_start.isoformat():
        # 缓存的完整序列已覆盖请求区间（含预热）→ 本地切片，不再访问数据源
        pairs = list(zip(series["dates"], series["items"]))
        target = [(d, item) for d, item in pairs if start_text <= d <= end_text]
        warm = [(d, item) for d, item in pairs if d < start_text]
        warm = warm[-warmup_bars:] if warmup_bars else []
        if not target:
            raise LookupError(f"{code} 在 {start_date} 至 {end_date} 没有 K 线数据")
        if limit is not None:
            target = target[-fetch_limit:]
        return {
            "code": code,
            "name": get_name(code),
            "period": period,
            "limit": fetch_limit,
            "source": series["source"],
            "requested_start_date": start_text,
            "requested_end_date": end_text,
            "actual_start_date": target[0][0],
            "actual_end_date": target[-1][0],
            "dates": [d for d, _ in target],
            "items": [item for _, item in target],
            "warmup": [{"date": d, **item} for d, item in warm],
        }

    # 缓存窗口不足（请求更早的历史）→ 按所需区间回源
    frame, source = _fetch_kline_frame(code, period, fetch_start, fetch_end, fetch_limit)
    frame = frame[(frame["date"] >= fetch_start.isoformat()) & (frame["date"] <= end_text)]
    if limit is not None:
        frame = frame.tail(fetch_limit)
    target_df = frame[frame["date"] >= start_text]
    warmup_df = frame[frame["date"] < start_text].tail(warmup_bars)
    if target_df.empty:
        raise LookupError(f"{code} 在 {start_date} 至 {end_date} 没有 K 线数据")

    dates = target_df["date"].tolist()
    items = [_row_to_item(row) for _, row in target_df.iterrows()]
    warmup = [
        {"date": row["date"], **_row_to_item(row)}
        for _, row in warmup_df.iterrows()
    ]
    return {
        "code": code,
        "name": get_name(code),
        "period": period,
        "limit": fetch_limit,
        "source": source,
        "requested_start_date": start_text,
        "requested_end_date": end_text,
        "actual_start_date": dates[0],
        "actual_end_date": dates[-1],
        "dates": dates,
        "items": items,
        "warmup": warmup,
    }
