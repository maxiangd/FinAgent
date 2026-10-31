"""行情快照：报价、行业、股息率，以及价格兜底。"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import akshare as ak
import pandas as pd

from ..common.cache_manager import _num, _retry, cached
from ..analysis.fundamental_data_service import _get_financial
from .kline_data_service import get_kline
from .stock_name_service import get_name
from ..analysis.news_data_service import _get_news

logger = logging.getLogger("finagent.market.snapshot")

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
