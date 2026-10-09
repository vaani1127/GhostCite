from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from ghostcite.search.budget import CombinedBudget, SearchBudget
from ghostcite.search.cache import CACHE_FILE_NAME, SqliteCache, cache_key
from ghostcite.search.ratelimit import RateLimiter
from ghostcite.search.sanitize import sanitize_response

PARAMS = {"engine": "google_scholar", "q": '"Attention is all you need"', "hl": "en"}


class FakeClock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


# ---------------------------------------------------------------- cache


def test_cache_key_ignores_order_and_api_key() -> None:
    reordered = dict(reversed(list(PARAMS.items())))
    assert cache_key(PARAMS) == cache_key(reordered)
    assert cache_key(PARAMS) == cache_key({**PARAMS, "api_key": "secret-value-1"})
    assert cache_key(PARAMS) != cache_key({**PARAMS, "q": "other"})


def test_cache_round_trip_and_ttl(tmp_path: Path) -> None:
    clock = FakeClock()
    with SqliteCache(tmp_path / "c", ttl_seconds=60, clock=clock) as cache:
        assert cache.get(PARAMS) is None
        cache.put(PARAMS, {"organic_results": [{"title": "T\u00fcbingen"}]})
        assert cache.get(PARAMS) == {"organic_results": [{"title": "T\u00fcbingen"}]}
        assert cache.contains(PARAMS)
        clock.now += 61
        assert cache.get(PARAMS) is None
        assert cache.stats().expired == 1
    assert (tmp_path / "c" / CACHE_FILE_NAME).is_file()


def test_cache_put_replaces(tmp_path: Path) -> None:
    with SqliteCache(tmp_path, ttl_seconds=60) as cache:
        cache.put(PARAMS, {"v": 1})
        cache.put(PARAMS, {"v": 2})
        assert cache.get(PARAMS) == {"v": 2}
        assert cache.stats().entries == 1


def test_cache_persists_across_instances(tmp_path: Path) -> None:
    with SqliteCache(tmp_path, ttl_seconds=60) as cache:
        cache.put(PARAMS, {"v": 1})
    with SqliteCache(tmp_path, ttl_seconds=60) as cache:
        assert cache.get(PARAMS) == {"v": 1}


def test_cache_export_stats_clear(tmp_path: Path) -> None:
    with SqliteCache(tmp_path, ttl_seconds=60) as cache:
        other = {**PARAMS, "q": "second"}
        cache.put(PARAMS, {"v": 1})
        cache.put(other, {"v": 2})
        exported = cache.export([cache_key(PARAMS), cache_key(PARAMS), "missing"])
        assert exported == {cache_key(PARAMS): {"v": 1}}
        stats = cache.stats()
        assert (stats.entries, stats.expired) == (2, 0)
        assert stats.size_bytes > 0
        assert cache.clear() == 2
        assert cache.stats().entries == 0


def test_cache_is_thread_safe(tmp_path: Path) -> None:
    with SqliteCache(tmp_path, ttl_seconds=60) as cache:

        def worker(n: int) -> None:
            for i in range(20):
                params = {**PARAMS, "q": f"{n}-{i}"}
                cache.put(params, {"n": n, "i": i})
                assert cache.get(params) == {"n": n, "i": i}

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert cache.stats().entries == 160


# ---------------------------------------------------------------- sanitize


def test_sanitize_removes_account_links_and_keys() -> None:
    response: dict[str, Any] = {
        "search_metadata": {
            "id": "abc",
            "json_endpoint": "https://serpapi.com/searches/abc.json",
            "raw_html_file": "https://serpapi.com/searches/abc.html",
        },
        "search_parameters": {"engine": "google_scholar", "api_key": "leaked-value"},
        "organic_results": [{"link": "https://serpapi.com/search?api_key=leaked-value&q=x"}],
        "count": 3,
    }
    clean = sanitize_response(response)
    assert clean["search_metadata"] == {"id": "abc"}
    assert "api_key" not in clean["search_parameters"]
    assert "leaked-value" not in str(clean)
    assert clean["count"] == 3
    assert response["search_parameters"]["api_key"] == "leaked-value"  # input untouched


# ---------------------------------------------------------------- budget


def test_budget_caps_and_refunds() -> None:
    budget = SearchBudget(2)
    assert budget.reserve()
    assert budget.reserve()
    assert not budget.reserve()
    assert (budget.used, budget.remaining) == (2, 0)
    budget.refund()
    assert budget.remaining == 1
    budget.refund()
    budget.refund()  # never below zero
    assert budget.used == 0


def test_zero_budget_and_validation() -> None:
    assert not SearchBudget(0).reserve()
    with pytest.raises(ValueError, match="negative"):
        SearchBudget(-1)
    with pytest.raises(ValueError, match="at least one"):
        CombinedBudget([])


def test_budget_is_thread_safe() -> None:
    budget = SearchBudget(50)
    granted: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(20):
            ok = budget.reserve()
            with lock:
                granted.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert granted.count(True) == 50
    assert budget.used == 50


def test_combined_budget_is_all_or_nothing() -> None:
    job, shared = SearchBudget(5), SearchBudget(1)
    combined = CombinedBudget([job, shared])
    assert combined.reserve()
    assert not combined.reserve()  # the shared budget refuses...
    assert job.used == 1  # ...and the job's reservation is rolled back
    combined.refund()
    assert (job.used, shared.used, combined.used) == (0, 0, 0)


# ---------------------------------------------------------------- rate limiter


def test_rate_limiter_allows_a_burst_then_paces() -> None:
    clock = FakeClock()
    limiter = RateLimiter(3600, clock=clock, sleep=clock.sleep)  # one token per second
    waits = [limiter.acquire() for _ in range(3602)]
    assert waits[:3600] == [0.0] * 3600
    assert waits[3600:] == pytest.approx([1.0, 1.0])


def test_rate_limiter_refills_over_time() -> None:
    clock = FakeClock()
    limiter = RateLimiter(2, clock=clock, sleep=clock.sleep)  # capacity 2, one per 30 min
    assert [limiter.acquire(), limiter.acquire()] == [0.0, 0.0]
    clock.now += 1800
    assert limiter.acquire() == 0.0
    assert limiter.acquire() == pytest.approx(1800.0)


def test_rate_limiter_validation() -> None:
    with pytest.raises(ValueError, match="positive"):
        RateLimiter(0)
