"""缓存装饰器：同键单飞、TTL 过期与空结果短缓存。"""

import threading
import time

import services.common.cache_manager as cache


def setup_function():
    cache._backend = cache.MemoryCacheBackend()
    cache._key_locks.clear()


def test_concurrent_misses_fetch_once():
    calls = {"n": 0}

    @cache.cached("single-flight", 60)
    def load(value):
        calls["n"] += 1
        time.sleep(0.1)
        return value * 2

    results = []
    threads = [threading.Thread(target=lambda: results.append(load(3))) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls["n"] == 1
    assert results == [6] * 5


def test_ttl_expires():
    calls = {"n": 0}

    @cache.cached("ttl", 0.05)
    def load():
        calls["n"] += 1
        return calls["n"]

    assert load() == 1
    assert load() == 1
    time.sleep(0.1)
    assert load() == 2


def test_empty_result_uses_shorter_ttl():
    calls = {"n": 0}

    @cache.cached("empty", 60, ttl_empty=0.05)
    def load():
        calls["n"] += 1
        return [] if calls["n"] == 1 else ["data"]

    assert load() == []
    time.sleep(0.1)
    assert load() == ["data"]
