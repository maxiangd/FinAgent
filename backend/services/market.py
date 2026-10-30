"""AKShare 市场数据封装，负责获取行情并整理成前端需要的结构。

数据来源：
- 股票名称：东财代码表。
- K 线：新浪为主，东财为备用。
- 财务指标：新浪财务指标接口。
- 行情报价：腾讯行情；报价缺失时用 K 线收盘价兜底。
- 新闻：东财个股新闻，保留原始标题供后续分析。
- 行业和分红：巨潮资讯接口。

查询结果按数据类型缓存在当前 Python 进程中。

对外契约：
- get_kline      -> { code, name, dates[], items[{open,close,high,low,volume}] }
- get_snapshot   -> { code, name, industry, marketCap, price, changePct,
                      pe, pb, roe, revGrowth, profitGrowth, margin, dividendYield,
                      news[], meta }
"""
from __future__ import annotations

import logging
import re
import threading
import time
from datetime import date, timedelta

import akshare as ak
import pandas as pd

logger = logging.getLogger("finagent.market")

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


# ---------- K线（新浪 → 腾讯 → 东财，依次回退） ----------
_SINA_COLS = {"date": "date", "open": "open", "close": "close", "high": "high", "low": "low", "volume": "volume"}
_EM_COLS = {"date": "日期", "open": "开盘", "close": "收盘", "high": "最高", "low": "最低", "volume": "成交量"}


@cached("kline", 300)
def get_kline(code: str, limit: int = 520):
    """获取日 K 线。新浪为主源，腾讯次之，东财兜底。"""
    code = code.strip()
    end = date.today()
    start = end - timedelta(days=1100)
    s, e = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

    if code.startswith(("6", "9")):
        prefix = "sh"
    elif code.startswith(("0", "2", "3")):
        prefix = "sz"
    else:
        prefix = "bj"
    symbol = prefix + code

    sources = [
        ("新浪", lambda: ak.stock_zh_a_daily(symbol=symbol, start_date=s, end_date=e, adjust="qfq"), _SINA_COLS),
        ("腾讯", lambda: ak.stock_zh_a_hist_tx(symbol=symbol, start_date=s, end_date=e, adjust="qfq"), _SINA_COLS),
        ("东财", lambda: ak.stock_zh_a_hist(symbol=code, period="daily", start_date=s, end_date=e, adjust="qfq"), _EM_COLS),
    ]

    df, cols, errors = None, None, []
    for name, fetch, colmap in sources:
        try:
            df = _retry(fetch, delay=0.8)
            cols = colmap
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            logger.warning("%s %s K线失败（%s）", code, name, f"{type(exc).__name__}: {exc}")

    if df is None or df.empty:
        raise LookupError(f"{code} 未获取到 K 线数据 | " + " | ".join(errors))

    df = df.tail(limit)
    dates = df[cols["date"]].astype(str).str[:10].tolist()
    items = []
    for _, row in df.iterrows():
        items.append({
            "open": _num(row[cols["open"]]),
            "close": _num(row[cols["close"]]),
            "high": _num(row[cols["high"]]),
            "low": _num(row[cols["low"]]),
            "volume": _num(row[cols["volume"]], 0),
        })

    return {"code": code, "name": get_name(code), "dates": dates, "items": items}


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
