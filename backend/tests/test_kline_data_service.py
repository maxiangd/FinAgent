"""K 线取数：默认序列只取一次，区间请求本地切片，超出窗口才回源。"""

import pandas as pd
import pytest

import services.common.cache_manager as cache
import services.market.kline_data_service as kline


def _frame(start="2026-01-01", periods=40):
    dates = pd.bdate_range(start, periods=periods).strftime("%Y-%m-%d")
    return pd.DataFrame(
        {
            "date": dates,
            "open": [10.0] * periods,
            "close": [10.5] * periods,
            "high": [11.0] * periods,
            "low": [9.5] * periods,
            "volume": [1000.0] * periods,
        }
    )


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    cache._backend = cache.MemoryCacheBackend()
    cache._key_locks.clear()
    monkeypatch.setattr(kline, "get_name", lambda code: "测试股票")


def test_range_request_slices_cached_series(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(code, period, fetch_start, fetch_end, fetch_limit):
        calls["n"] += 1
        return _frame(), "测试源"

    monkeypatch.setattr(kline, "_fetch_kline_frame", fake_fetch)

    full = kline.get_kline("600519")
    assert calls["n"] == 1
    assert full["source"] == "测试源"

    start = full["dates"][20]
    end = full["dates"][24]
    sliced = kline.get_kline("600519", start_date=start, end_date=end, warmup_bars=3)

    assert calls["n"] == 1  # 命中缓存，不再访问数据源
    assert sliced["dates"][0] == start
    assert sliced["dates"][-1] == end
    assert len(sliced["warmup"]) == 3


def test_range_outside_window_refetches(monkeypatch):
    frames = [_frame("2026-01-01"), _frame("2016-01-04")]
    calls = {"n": 0}

    def fake_fetch(code, period, fetch_start, fetch_end, fetch_limit):
        calls["n"] += 1
        return frames[min(calls["n"] - 1, len(frames) - 1)], "测试源"

    monkeypatch.setattr(kline, "_fetch_kline_frame", fake_fetch)

    kline.get_kline("600519")
    assert calls["n"] == 1

    result = kline.get_kline(
        "600519", start_date="2016-02-01", end_date="2016-03-31", warmup_bars=5
    )
    assert calls["n"] == 2  # 缓存窗口覆盖不到，回源
    assert result["dates"][0] >= "2016-02-01"
    assert result["dates"][-1] <= "2016-03-31"
