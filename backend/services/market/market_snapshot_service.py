"""行情快照：报价、行业、股息率，以及价格兜底。"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import akshare as ak
import pandas as pd
import requests

from ..analysis.fundamental_data_service import _get_financial
from ..analysis.news_data_service import _get_news
from ..common.cache_manager import _num, _retry, cached
from .kline_data_service import get_kline
from .stock_name_service import get_name

logger = logging.getLogger("finagent.market.snapshot")

_QUOTE_URL = "https://qt.gtimg.cn/q={symbol}"
_QUOTE_HEADERS = {"Referer": "https://gu.qq.com/", "User-Agent": "Mozilla/5.0"}


def _tx_symbol(code: str) -> str:
    if code.startswith(("6", "9")):
        return f"sh{code}"
    if code.startswith(("0", "2", "3")):
        return f"sz{code}"
    return f"bj{code}"


# ---------- 报价：腾讯单只行情（一次请求，替代原来的全市场表） ----------
@cached("quote_tx", 60, ttl_empty=30)
def _get_quote_tx(code: str) -> dict:
    """返回名称、价格、涨跌幅、量比、换手率、PE、PB 和总市值（亿元）。"""
    try:
        resp = requests.get(
            _QUOTE_URL.format(symbol=_tx_symbol(code)),
            timeout=8,
            headers=_QUOTE_HEADERS,
        )
        resp.encoding = "gbk"
        text = resp.text.strip()
        if '"' not in text:
            return {}
        parts = text.split('"')[1].split("~")
        if len(parts) < 50:
            return {}

        def pick(index: int, digits: int = 2):
            return _num(parts[index], digits)

        return {
            "name": parts[1].strip() or None,
            "price": pick(3),
            "change_pct": pick(32),
            "vol_ratio": pick(49),   # 量比
            "turnover": pick(38),    # 换手率 %
            "pe": pick(39),          # PE(TTM)
            "pb": pick(46),
            "market_cap": pick(45, 0),  # 总市值，单位：亿元
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
    """组装前端兼容快照；报价、财务、新闻、行业并行获取。"""
    code = code.strip()
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="snapshot") as pool:
        financial_future = pool.submit(_get_financial, code)
        news_future = pool.submit(_get_news, code)
        quote_future = pool.submit(_get_quote_tx, code)
        industry_future = pool.submit(_get_industry, code)
        financial = financial_future.result()
        news = news_future.result()
        quote = quote_future.result()
        industry = industry_future.result()

    price = quote.get("price")
    change_pct = quote.get("change_pct")
    if price is None or change_pct is None:
        # 腾讯行情缺失时才回退到 K 线收盘价
        try:
            items = get_kline(code, 2)["items"]
            last_close = items[-1]["close"]
            prev_close = items[-2]["close"] if len(items) > 1 else last_close
            price = price if price is not None else last_close
            if change_pct is None and prev_close:
                change_pct = round((last_close - prev_close) / prev_close * 100, 2)
        except Exception as e:  # noqa: BLE001
            logger.warning("%s 快照价格兜底失败: %s: %s", code, type(e).__name__, e)

    dividend_yield = _get_dividend_yield(code, price)

    return {
        "code": code,
        "name": quote.get("name") or get_name(code),
        "industry": industry,
        "marketCap": _fmt_cap(quote.get("market_cap")),
        "price": price,
        "changePct": change_pct,
        "pe": quote.get("pe"),
        "pb": quote.get("pb"),
        "volRatio": quote.get("vol_ratio"),
        "turnover": quote.get("turnover"),
        "roe": financial.get("roe"),
        "revGrowth": financial.get("revGrowth"),
        "profitGrowth": financial.get("profitGrowth"),
        "margin": financial.get("margin"),
        "dividendYield": dividend_yield,
        "news": news,
        "meta": {"source": "akshare", "note": "腾讯单只行情 + 巨潮行业/分红 + 新浪财务"},
    }
