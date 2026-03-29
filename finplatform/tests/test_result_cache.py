import threading
import pytest
from finplatform.result_cache import ResultCache


EXPECTED_KEYS = {"market_sentiment", "sector_strength", "institutional_flows", "ai_signals"}


def test_get_returns_none_for_uninitialised_keys():
    cache = ResultCache()
    for key in EXPECTED_KEYS:
        assert cache.get(key) is None


def test_set_then_get_returns_correct_value():
    cache = ResultCache()
    cache.set("market_sentiment", {"score": 0.75, "label": "bullish"})
    assert cache.get("market_sentiment") == {"score": 0.75, "label": "bullish"}


def test_snapshot_returns_all_four_keys():
    cache = ResultCache()
    snap = cache.snapshot()
    assert set(snap.keys()) == EXPECTED_KEYS


def test_snapshot_reflects_set_values():
    cache = ResultCache()
    cache.set("ai_signals", {"direction": "up"})
    snap = cache.snapshot()
    assert snap["ai_signals"] == {"direction": "up"}
    # other keys still None
    assert snap["market_sentiment"] is None


def test_concurrent_set_get_does_not_raise():
    cache = ResultCache()
    errors = []

    def writer(i):
        try:
            cache.set("market_sentiment", {"value": i})
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            val = cache.get("market_sentiment")
            # value must be None or a dict — never a partial/corrupt object
            assert val is None or isinstance(val, dict)
        except Exception as e:
            errors.append(e)

    threads = []
    for i in range(10):
        threads.append(threading.Thread(target=writer, args=(i,)))
        threads.append(threading.Thread(target=reader))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Errors raised during concurrent access: {errors}"
