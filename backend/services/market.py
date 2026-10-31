"""AKShare 市场数据封装，负责获取行情并整理成前端需要的结构。

数据来源：
- 股票名称：东财代码表。
- K 线：日线新浪为主、腾讯/东财备用；周/月线雪球为主、腾讯备用（东财行情接口在部分网络下不可达）。
- 财务指标：新浪财务指标接口。
- 行情报价：腾讯行情；报价缺失时用 K 线收盘价兜底。
- 新闻：东财个股新闻，保留原始标题供后续分析。
- 行业和分红：巨潮资讯接口。

查询结果按数据类型缓存在当前 Python 进程中。

对外契约：
- get_kline      -> { code, name, period, source, dates[], items[], warmup[], requested/actual date range }
- get_snapshot   -> { code, name, industry, marketCap, price, changePct,
                      pe, pb, roe, revGrowth, profitGrowth, margin, dividendYield,
                      news[], meta }
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from math import ceil
from pathlib import Path

import akshare as ak
import pandas as pd
import requests
from dotenv import load_dotenv

logger = logging.getLogger("finagent.market")

# 从项目根目录读取 .env，不受启动 Uvicorn 时所在目录影响。
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


def _kline_limit_from_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning("%s must be an integer; using default %s", name, default)
        value = default
    return min(max(value, 1), 5000)


KLINE_LIMITS = {
    "daily": _kline_limit_from_env("KLINE_DAILY_LIMIT", 520),
    "weekly": _kline_limit_from_env("KLINE_WEEKLY_LIMIT", 260),
    "monthly": _kline_limit_from_env("KLINE_MONTHLY_LIMIT", 120),
}

# ---------- 进程级缓存（TTL） ----------
_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def _is_empty(v) -> bool:
    """判断查询结果是否为空（DataFrame/Series 不能直接取 bool）。"""
    if v is None:
        return True
    if isinstance(v, (pd.DataFrame, pd.Series)):
        return v.empty
    if isinstance(v, (list, tuple, dict, set, str)):
        return len(v) == 0
    return False


def cached(key: str, ttl: float, ttl_empty: float = 0):
    """为数据查询函数添加按秒计时的进程内缓存。

    ttl_empty>0 时，空结果（None/{} /[]）只按更短的 ttl_empty 缓存，
    避免一次网络抖动把"没有数据"冻住整个缓存周期（如代码表 24 小时）。
    """
    def deco(fn):
        """接收原函数并返回带缓存的版本。"""
        def wrapper(*a, **kw):
            """缓存命中时直接返回旧结果，否则查询并保存新结果。"""
            k = f"{key}:{a}:{sorted(kw.items())}"
            with _lock:
                hit = _cache.get(k)
                if hit and time.time() - hit[0] < hit[2]:
                    return hit[1]
            val = fn(*a, **kw)
            life = ttl_empty if (ttl_empty and _is_empty(val)) else ttl
            with _lock:
                _cache[k] = (time.time(), val, life)
            return val
        return wrapper
    return deco


def _retry(fn, times: int = 3, delay: float = 1.2):
    """调用 fn；失败后按递增间隔重试，最终失败时抛出最后一个异常。"""
    last = None
    for i in range(times):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(delay * (i + 1))
    raise last


def _num(v, nd: int = 2):
    """把数据源中的值转为指定精度的数字；无效值返回 None。"""
    if v is None:
        return None
    try:
        number = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return round(number, nd)


def _fcol(df, key: str, default=None):
    """按列名包含匹配取值（最新一行）。"""
    for c in df.columns:
        if key in str(c):
            v = df.iloc[-1][c]
            return default if pd.isna(v) else v
    return default


# ---------- 股票名称（东财代码表） ----------
@cached("code_name", 86400, ttl_empty=60)
def _code_name_table() -> dict[str, str]:
    """获取并缓存股票代码到名称的映射表。"""
    try:
        df = _retry(ak.stock_info_a_code_name, times=2)
        return dict(zip(df["code"].astype(str), df["name"].astype(str)))
    except Exception as e:  # noqa: BLE001
        logger.warning("代码表获取失败: %s: %s", type(e).__name__, e)
        return {}


def get_name(code: str) -> str:
    """根据股票代码查名称；代码表没有该股票时返回原代码。"""
    return _code_name_table().get(code.strip(), code)


# ---------- 股票搜索（代码精确 / 名称模糊） ----------
@cached("search", 60)
def search_stock(q: str, limit: int = 8) -> list[dict]:
    """按代码（6位精确）或名称（子串匹配）搜索，返回候选 [{code, name}]。"""
    table = _code_name_table()
    if not table:
        return []
    q = str(q or "").strip().replace(" ", "").lower()
    if not q:
        return []

    exact_code = []
    if q.isdigit() and len(q) == 6 and q in table:
        exact_code = [{"code": q, "name": table[q]}]

    name_matches = [
        {"code": c, "name": n}
        for c, n in table.items()
        if q in n.lower().replace(" ", "")
    ]
    # 精确名称排最前，其余按代码顺序
    name_matches.sort(key=lambda x: (x["name"].lower() != q, x["code"]))
    candidates = exact_code + name_matches
    # 去重（代码精确命中同时被名称子串命中）
    seen, out = set(), []
    for c in candidates:
        if c["code"] not in seen:
            seen.add(c["code"])
            out.append(c)
    return out[:limit]


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


@cached("kline", 300)
def get_kline(
    code: str,
    limit=None,
    period: str = "daily",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    warmup_bars: int = 0,
):
    """获取指定周期 K 线；可按日期筛选，并为指标计算额外返回预热 K 线。"""
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
    if start_date and end_date:
        fetch_start = start_date - timedelta(days=int(warmup_bars * days_per_bar) + 10)
        fetch_end = end_date
        # 根据自然日跨度估算所需 K 线根数，并留出节假日和周期边界余量。
        calendar_days_per_bar = {"daily": 1.5, "weekly": 7.5, "monthly": 31}[period]
        required_limit = ceil((fetch_end - fetch_start).days / calendar_days_per_bar) + 20
        if required_limit > 5000:
            raise ValueError("日期范围过长，请缩短区间后重试")
        fetch_limit = min(required_limit, configured_limit) if limit is not None else required_limit
    else:
        fetch_end = date.today()
        lookback_days = max(1100 if period == "daily" else 0, int(configured_limit * days_per_bar) + 45)
        fetch_start = fetch_end - timedelta(days=lookback_days)
        fetch_limit = configured_limit

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

    df, cols, errors = None, None, []

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

    df = df.copy()
    df["_normalized_date"] = pd.to_datetime(df[cols["date"]], errors="coerce").dt.strftime("%Y-%m-%d")
    df = df[df["_normalized_date"].notna()].sort_values("_normalized_date")
    if start_date and end_date:
        normalized_start = fetch_start.isoformat()
        normalized_end = end_date.isoformat()
        df = df[
            (df["_normalized_date"] >= normalized_start)
            & (df["_normalized_date"] <= normalized_end)
        ]
        if limit is not None:
            df = df.tail(fetch_limit)
        if df.empty:
            raise LookupError(f"{code} 在 {start_date} 至 {end_date} 没有 K 线数据")
        target_df = df[df["_normalized_date"] >= start_date.isoformat()]
        warmup_df = df[df["_normalized_date"] < start_date.isoformat()].tail(warmup_bars)
        if target_df.empty:
            raise LookupError(f"{code} 在 {start_date} 至 {end_date} 没有 K 线数据")
    else:
        df = df.tail(configured_limit)
        target_df = df
        warmup_df = df.iloc[0:0]

    def row_to_item(row):
        return {
            "open": _num(row[cols["open"]]),
            "close": _num(row[cols["close"]]),
            "high": _num(row[cols["high"]]),
            "low": _num(row[cols["low"]]),
            "volume": _num(row[cols["volume"]], 0),
        }

    dates = target_df["_normalized_date"].tolist()
    items = [row_to_item(row) for _, row in target_df.iterrows()]
    warmup = [
        {"date": row["_normalized_date"], **row_to_item(row)}
        for _, row in warmup_df.iterrows()
    ]

    return {
        "code": code,
        "name": get_name(code),
        "period": period,
        "limit": fetch_limit if start_date else configured_limit,
        "source": source,
        "requested_start_date": start_date.isoformat() if start_date else None,
        "requested_end_date": end_date.isoformat() if end_date else None,
        "actual_start_date": dates[0],
        "actual_end_date": dates[-1],
        "dates": dates,
        "items": items,
        "warmup": warmup,
    }


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


def _to_iso_date(value) -> str | None:
    """把数据源日期转换为 YYYY-MM-DD；无效值返回 None。"""
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _cell_text(value) -> str:
    """把表格单元格转成干净文本；空值返回空字符串。"""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


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


# ---------- 报价补充：腾讯全市场（PE/总市值/流通市值/价格/涨跌幅） ----------
@cached("tx_spot", 3600)
def _tx_spot_table() -> pd.DataFrame:
    """获取并缓存腾讯 A 股行情表，同时标准化股票代码列。"""
    df = _retry(lambda: ak.stock_zh_a_spot_tx(), times=2)
    df["_code"] = df["code"].astype(str).str.lower()
    return df


def _get_quote_tx(code: str) -> dict:
    """腾讯行情：pe_ttm / zsz(总市值,元) / ltsz(流通市值) / zxj(最新价) / zdf(涨跌幅) / name"""
    try:
        tbl = _tx_spot_table()
        row = tbl[tbl["_code"].str.endswith(code.lower())]
        if row.empty:
            return {}
        r = row.iloc[0]
        return {
            "name": str(r.get("name", "")).strip() or None,
            "pe": _num(r.get("pe_ttm")),
            "market_cap": _num(r.get("zsz")),  # 腾讯返回单位：亿元
            "price": _num(r.get("zxj")),
            "change_pct": _num(r.get("zdf")),
            "vol_ratio": _num(r.get("lb")),    # 量比：当日成交 vs 近5日均量
            "turnover": _num(r.get("hsl")),    # 换手率 %
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("%s 腾讯行情获取失败: %s: %s", code, type(e).__name__, e)
        return {}


# ---------- 行业（巨潮公司资料，按个股拉取并缓存） ----------
@cached("industry", 86400, ttl_empty=60)
def _get_industry(code: str):
    """从巨潮公司资料中查找股票所属行业。"""
    try:
        df = _retry(lambda: ak.stock_profile_cninfo(symbol=code), times=2)
        if df is None or df.empty or "A股代码" not in df.columns:
            return None
        row = df[df["A股代码"].astype(str) == code.strip()]
        if row.empty:
            return None
        v = row.iloc[0].get("所属行业")
        if pd.isna(v):
            return None
        industry = str(v).strip()
        return industry or None
    except Exception as e:  # noqa: BLE001
        logger.warning("%s 行业获取失败: %s: %s", code, type(e).__name__, e)
        return None


# ---------- 股息率（巨潮分红，TTM 口径：最近 365 天实际派息合计 / 最新价） ----------
@cached("dividend", 86400, ttl_empty=60)
def _get_dividend_yield(code: str, price):
    """TTM 股息率：派息日落在最近 365 天内的每股现金分红合计 ÷ 当前价 × 100。

    注意：A股不少公司一年多次分红（年报 + 中期/季度/特别），
    只取"最新一条"会把股息率低估一半以上，必须累加。
    """
    try:
        df = _retry(lambda: ak.stock_dividend_cninfo(symbol=code), times=2)
        if df is None or df.empty:
            return None
        cutoff = (date.today() - timedelta(days=365)).strftime("%Y-%m-%d")
        total = 0.0
        for _, r in df.iterrows():
            ratio = pd.to_numeric(r.get("派息比例"), errors="coerce")
            if not (pd.notna(ratio) and ratio > 0):
                continue
            # 注意：str(NaN) == 'nan'，直接参与字符串比较会恒为 True，必须先判空
            pay_date = str(r.get("派息日") or "").strip()
            ann_date = str(r.get("实施方案公告日期") or "").strip()
            ref = pay_date if pay_date not in ("", "nan", "None") else ann_date
            if len(ref) >= 10 and ref[:10] >= cutoff:
                total += ratio
        if total <= 0 or not price:
            return None
        return round(total / 10 / price * 100, 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("%s 分红获取失败: %s: %s", code, type(e).__name__, e)
        return None


def _fmt_cap(yuan):
    """市值显示（输入单位：亿元）。"""
    if yuan is None:
        return None
    if yuan >= 10000:
        return f"{yuan / 10000:.2f}万亿"
    return f"{yuan:.0f}亿"


def get_snapshot(code: str) -> dict:
    """组装前端兼容快照。价格由腾讯行情提供，K线兜底保证可用。"""
    code = code.strip()
    financial = _get_financial(code)
    news = _get_news(code)
    quote = _get_quote_tx(code)

    # 价格兜底：K线最后两根（腾讯行情失败时保证可用）
    price = quote.get("price")
    change_pct = quote.get("change_pct")
    try:
        # 取最近两根 K 线：在腾讯报价缺失时补充价格和涨跌幅。
        kl = get_kline(code, 3)
        items = kl["items"]
        last_close = items[-1]["close"]
        prev_close = items[-2]["close"] if len(items) > 1 else last_close
        price = price if price is not None else last_close
        if change_pct is None and prev_close:
            change_pct = round((last_close - prev_close) / prev_close * 100, 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("%s 快照价格兜底失败: %s: %s", code, type(e).__name__, e)

    industry = _get_industry(code)
    dividend_yield = _get_dividend_yield(code, price)

    return {
        "code": code,
        "name": quote.get("name") or get_name(code),
        "industry": industry,
        "marketCap": _fmt_cap(quote.get("market_cap")),
        "price": price,
        "changePct": change_pct,
        "pe": quote.get("pe"),
        "pb": None,
        "volRatio": quote.get("vol_ratio"),
        "turnover": quote.get("turnover"),
        "roe": financial.get("roe"),
        "revGrowth": financial.get("revGrowth"),
        "profitGrowth": financial.get("profitGrowth"),
        "margin": financial.get("margin"),
        "dividendYield": dividend_yield,
        "news": news,
        "meta": {"source": "akshare", "note": "腾讯行情 + 巨潮行业/分红 + 新浪财务"},
    }
