"""缓存后端（进程内 / Redis），以及重试、数值整理等通用工具。"""
from __future__ import annotations

import logging
import pickle
import re
import threading
import time
from typing import Any

import pandas as pd

from config.settings import get_env_str

logger = logging.getLogger("finagent.cache")


def _is_empty(v) -> bool:
    """判断查询结果是否为空（DataFrame/Series 不能直接取 bool）。"""
    if v is None:
        return True
    if isinstance(v, (pd.DataFrame, pd.Series)):
        return v.empty
    if isinstance(v, (list, tuple, dict, set, str)):
        return len(v) == 0
    return False


class MemoryCacheBackend:
    """进程内字典缓存，带 TTL。"""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[bool, Any]:
        """返回 (是否命中, 值)；过期视作未命中。"""
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return False, None
            expire_at, value = hit
            if time.time() >= expire_at:
                self._data.pop(key, None)
                return False, None
            return True, value

    def set(self, key: str, value: Any, ttl: float) -> None:
        with self._lock:
            self._data[key] = (time.time() + ttl, value)


class RedisCacheBackend:
    """Redis 缓存；值用 pickle 序列化，只适用于本地可信部署。"""

    def __init__(self, client, prefix: str = "finagent:cache:") -> None:
        self._client = client
        self._prefix = prefix

    def get(self, key: str) -> tuple[bool, Any]:
        try:
            raw = self._client.get(self._prefix + key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("读取 Redis 失败：%s (%s)", key, exc)
            return False, None
        if raw is None:
            return False, None
        try:
            return True, pickle.loads(raw)
        except Exception:  # noqa: BLE001
            logger.warning("缓存反序列化失败，已忽略：%s", key)
            return False, None

    def set(self, key: str, value: Any, ttl: float) -> None:
        try:
            payload = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:  # noqa: BLE001
            logger.warning("结果无法序列化，跳过缓存：%s (%s)", key, exc)
            return
        try:
            self._client.setex(self._prefix + key, max(int(ttl), 1), payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("写入 Redis 失败：%s (%s)", key, exc)


_backend = None
_backend_lock = threading.Lock()


def get_cache_backend():
    """返回缓存后端；首次调用时按配置初始化，Redis 不可用则回退内存。"""
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                _backend = _build_backend()
    return _backend


def _mask_redis_url(url: str) -> str:
    """日志里隐藏 Redis 连接串中的密码。"""
    return re.sub(r"//[^@/]+@", "//***@", url)


def _build_backend():
    """按 CACHE_BACKEND 选择后端；Redis 连不上时降级为进程内缓存。"""
    choice = (get_env_str("CACHE_BACKEND", "memory") or "memory").lower()
    if choice != "redis":
        logger.info("缓存后端：进程内内存")
        return MemoryCacheBackend()
    url = get_env_str("REDIS_URL", "redis://127.0.0.1:6379/0")
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=1.5, socket_timeout=1.5)
        client.ping()
        logger.info("缓存后端：Redis（%s）", _mask_redis_url(url))
        return RedisCacheBackend(client)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis 不可用（%s），回退到进程内缓存：%s", type(exc).__name__, _mask_redis_url(url))
        return MemoryCacheBackend()


def cached(key: str, ttl: float, ttl_empty: float = 0):
    """为数据查询函数添加按秒计时的缓存。

    ttl_empty>0 时，空结果（None/{} /[]）只按更短的 ttl_empty 缓存，
    避免一次网络抖动把"没有数据"冻住整个缓存周期（如代码表 24 小时）。
    """
    def deco(fn):
        """接收原函数并返回带缓存的版本。"""
        def wrapper(*a, **kw):
            """缓存命中时直接返回旧结果，否则查询并保存新结果。"""
            cache_key = f"{key}:{a}:{sorted(kw.items())}"
            backend = get_cache_backend()
            found, value = backend.get(cache_key)
            if found:
                return value
            result = fn(*a, **kw)
            life = ttl_empty if (ttl_empty and _is_empty(result)) else ttl
            backend.set(cache_key, result, life)
            return result
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


# ---------- 数据源字段整理 ----------
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
