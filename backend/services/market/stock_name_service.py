"""股票代码表、名称查询与搜索。"""
from __future__ import annotations

import logging

import akshare as ak

from ..common.cache_manager import _retry, cached

logger = logging.getLogger("finagent.market.names")

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
