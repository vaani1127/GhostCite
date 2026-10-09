from __future__ import annotations

import random
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ghostcite.config import SearchConfig
from ghostcite.errors import BudgetExhaustedError, SearchServiceError
from ghostcite.search.backends import TransportError
from ghostcite.search.budget import SearchBudget
from ghostcite.search.cache import SqliteCache
from ghostcite.search.client import ResponseSource, SearchClient
from ghostcite.search.ratelimit import RateLimiter

PARAMS = {"engine": "google_scholar", "q": '"A title"', "hl": "en"}
BODY = {"organic_results": [{"title": "A title"}]}
NOW = datetime(2026, 10, 9, 4, 6, 0, tzinfo=UTC)


class ScriptedTransport:
    """Returns or raises the scripted outcomes in order."""

    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def search(self, params: Mapping[str, str]) -> dict[str, Any]:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, dict)
        return outcome


class CountingLimiter(RateLimiter):
    def __init__(self) -> None:
        super().__init__(1000)
        self.acquired = 0

    def acquire(self) -> float:
        self.acquired += 1
        return 0.0


@pytest.fixture
def cache(tmp_path: Path) -> SqliteCache:
    return SqliteCache(tmp_path, ttl_seconds=3600)


def _client(
    cache: SqliteCache,
    transport: ScriptedTransport | None,
    budget: SearchBudget | None = None,
    **kwargs: Any,
) -> tuple[SearchClient, list[float]]:
    slept: list[float] = []
    client = SearchClient(
        cache,
        transport,
        budget or SearchBudget(10),
        cfg=SearchConfig(max_retries=3, backoff_base_seconds=1.0, backoff_cap_seconds=4.0),
        sleep=slept.append,
        rng=random.Random(7),  # noqa: S311 - seeded jitter for deterministic tests
        now=lambda: NOW,
        **kwargs,
    )
    return client, slept


def test_live_search_is_cached_and_counted(cache: SqliteCache) -> None:
    transport = ScriptedTransport(BODY)
    budget = SearchBudget(10)
    client, _ = _client(cache, transport, budget)

    first = client.search(PARAMS)
    second = client.search(PARAMS)

    assert (first.source, second.source) == (ResponseSource.LIVE, ResponseSource.CACHE)
    assert first.body == second.body == BODY
    assert transport.calls == 1
    assert budget.used == 1
    assert (client.live_searches, client.cache_hits) == (1, 1)
    assert client.is_cached(PARAMS)


def test_stored_responses_are_sanitized(cache: SqliteCache) -> None:
    raw = {**BODY, "search_metadata": {"id": "x", "json_endpoint": "https://serpapi.com/s.json"}}
    client, _ = _client(cache, ScriptedTransport(raw))
    client.search(PARAMS)
    assert cache.get(PARAMS) == {**BODY, "search_metadata": {"id": "x"}}


def test_offline_mode_never_spends(cache: SqliteCache) -> None:
    budget = SearchBudget(10)
    client, _ = _client(cache, None, budget)
    assert client.offline
    response = client.search(PARAMS)
    assert response.source is ResponseSource.MISS
    assert response.body is None
    assert budget.used == 0


def test_budget_exhaustion_stops_before_the_network(cache: SqliteCache) -> None:
    transport = ScriptedTransport(BODY)
    client, _ = _client(cache, transport, SearchBudget(0))
    with pytest.raises(BudgetExhaustedError):
        client.search(PARAMS)
    assert transport.calls == 0


def test_cache_hits_work_even_with_an_empty_budget(cache: SqliteCache) -> None:
    cache.put(PARAMS, BODY)
    client, _ = _client(cache, ScriptedTransport(), SearchBudget(0))
    assert client.search(PARAMS).body == BODY


def test_retries_with_jittered_exponential_backoff(cache: SqliteCache) -> None:
    transport = ScriptedTransport(
        TransportError("HTTP 503", retryable=True),
        TransportError("HTTP 429", retryable=True),
        TransportError("network error", retryable=True),
        BODY,
    )
    limiter = CountingLimiter()
    budget = SearchBudget(10)
    client, slept = _client(cache, transport, budget, limiter=limiter)

    assert client.search(PARAMS).body == BODY
    assert transport.calls == 4
    assert limiter.acquired == 4  # every attempt is paced
    assert len(slept) == 3
    for attempt, delay in enumerate(slept):
        assert 0.0 <= delay <= min(4.0, 2.0**attempt)
    assert budget.used == 1


def test_retries_exhausted_refunds_the_credit(cache: SqliteCache) -> None:
    transport = ScriptedTransport(*[TransportError("HTTP 500", retryable=True)] * 4)
    budget = SearchBudget(10)
    client, slept = _client(cache, transport, budget)
    with pytest.raises(SearchServiceError, match="after 4 attempt"):
        client.search(PARAMS)
    assert len(slept) == 3
    assert budget.used == 0
    assert not cache.contains(PARAMS)


def test_non_retryable_failure_stops_immediately(cache: SqliteCache) -> None:
    transport = ScriptedTransport(TransportError("bad", retryable=False), BODY)
    budget = SearchBudget(10)
    client, slept = _client(cache, transport, budget)
    with pytest.raises(SearchServiceError, match="after 1 attempt"):
        client.search(PARAMS)
    assert (transport.calls, slept, budget.used) == (1, [], 0)


def test_fatal_service_errors_propagate_and_refund(cache: SqliteCache) -> None:
    transport = ScriptedTransport(SearchServiceError("SerpApi rejected the API key (HTTP 401)."))
    budget = SearchBudget(10)
    client, _ = _client(cache, transport, budget)
    with pytest.raises(SearchServiceError, match="rejected"):
        client.search(PARAMS)
    assert budget.used == 0


def _timeout() -> TransportError:
    return TransportError("the request timed out", retryable=True, maybe_charged=True)


def test_timed_out_attempts_count_as_spent_credits(cache: SqliteCache) -> None:
    transport = ScriptedTransport(_timeout(), BODY)
    budget = SearchBudget(10)
    client, _ = _client(cache, transport, budget)
    assert client.search(PARAMS).body == BODY
    assert (client.live_searches, client.credits_used) == (1, 2)
    assert budget.used == 2


def test_budget_runs_out_while_retrying_a_timeout(cache: SqliteCache) -> None:
    transport = ScriptedTransport(_timeout(), BODY)
    budget = SearchBudget(1)
    client, _ = _client(cache, transport, budget)
    with pytest.raises(BudgetExhaustedError):
        client.search(PARAMS)
    assert transport.calls == 1
    assert (budget.used, client.credits_used) == (1, 1)


def test_unbilled_failures_keep_their_credit_for_the_retry(cache: SqliteCache) -> None:
    transport = ScriptedTransport(TransportError("HTTP 503", retryable=True), BODY)
    budget = SearchBudget(1)
    client, _ = _client(cache, transport, budget)
    assert client.search(PARAMS).body == BODY
    assert (budget.used, client.credits_used) == (1, 1)


def test_final_timeout_is_still_counted(cache: SqliteCache) -> None:
    transport = ScriptedTransport(*[_timeout()] * 4)
    budget = SearchBudget(10)
    client, _ = _client(cache, transport, budget)
    with pytest.raises(SearchServiceError, match="timed out"):
        client.search(PARAMS)
    assert (budget.used, client.credits_used, client.live_searches) == (4, 4, 0)


def _body_created(created_at: str) -> dict[str, Any]:
    return {**BODY, "search_metadata": {"id": "x", "status": "Success", "created_at": created_at}}


def test_retry_after_timeout_waits_at_least_the_timeout_delay(cache: SqliteCache) -> None:
    transport = ScriptedTransport(_timeout(), BODY)
    client, slept = _client(cache, transport)
    client.search(PARAMS)
    assert slept[0] >= 15.0  # SearchConfig default timeout_retry_delay_seconds


def test_retry_served_from_serpapi_cache_is_refunded(cache: SqliteCache) -> None:
    # The first request timed out but finished on SerpApi's side at 04:05:10; the
    # identical retry sent at 04:06:00 returns that original search (free cache hit).
    transport = ScriptedTransport(_timeout(), _body_created("2026-10-09 04:05:10 UTC"))
    budget = SearchBudget(10)
    client, _ = _client(cache, transport, budget)
    response = client.search(PARAMS)
    assert response.source is ResponseSource.LIVE
    assert (client.live_searches, client.credits_used, budget.used) == (1, 1, 1)


def test_fresh_retry_after_timeout_counts_both_attempts(cache: SqliteCache) -> None:
    transport = ScriptedTransport(_timeout(), _body_created("2026-10-09 04:06:01 UTC"))
    budget = SearchBudget(10)
    client, _ = _client(cache, transport, budget)
    client.search(PARAMS)
    assert (client.credits_used, budget.used) == (2, 2)


def test_recent_response_within_margin_is_not_treated_as_cached(cache: SqliteCache) -> None:
    # 5 s older than the request: within the 10 s clock-drift margin, so not proof of a cache hit.
    transport = ScriptedTransport(_timeout(), _body_created("2026-10-09 04:05:55 UTC"))
    client, _ = _client(cache, transport)
    client.search(PARAMS)
    assert client.credits_used == 2


def test_cache_detection_only_applies_after_a_timeout(cache: SqliteCache) -> None:
    # An old created_at on a first-attempt answer is SerpApi's cache from an earlier run:
    # free on SerpApi's side, but GhostCite cannot prove that, so it is counted (conservative).
    transport = ScriptedTransport(_body_created("2026-10-09 03:00:00 UTC"))
    client, _ = _client(cache, transport)
    client.search(PARAMS)
    assert client.credits_used == 1


def test_identical_params_are_resent_on_retry(cache: SqliteCache) -> None:
    seen: list[Mapping[str, str]] = []

    class RecordingTransport(ScriptedTransport):
        def search(self, params: Mapping[str, str]) -> dict[str, Any]:
            seen.append(dict(params))
            return super().search(params)

    client, _ = _client(cache, RecordingTransport(_timeout(), BODY))
    client.search(PARAMS)
    assert seen == [PARAMS, PARAMS]
    assert all("no_cache" not in params for params in seen)
