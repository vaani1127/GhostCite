"""The search client: cache first, then budget, pacing and retries for live searches.

Order of operations for one request:

1. A fresh cached (or demo-bundle) response is returned for free.
2. Without a transport (``--offline`` or ``--demo``), a cache miss returns no response.
3. One credit is reserved from the budget. If none is left, :class:`BudgetExhaustedError`
   tells the pipeline to mark the remaining references SKIPPED_BUDGET.
4. The rate limiter waits if the hourly allowance is used up.
5. The request is sent, and retryable failures back off exponentially with full jitter.
   A failure that SerpApi does not bill (an HTTP error or a refused connection) keeps
   the reserved credit for the retry. A timeout may have been billed even though no
   answer arrived, so that credit counts as spent and the retry must reserve a new one.
   This keeps ``--max-searches`` a true upper bound on billed searches.
   To avoid paying twice, the retry after a timeout waits at least
   ``timeout_retry_delay_seconds`` and resends exactly the same parameters (``no_cache``
   is never used). If SerpApi finished the first request in the meantime, the retry is
   answered free from its one-hour cache. That case is recognized from the response's
   original ``created_at``, and the retry's credit is refunded.
6. The sanitized response is cached.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from ghostcite.config import SEARCH, SearchConfig
from ghostcite.errors import BudgetExhaustedError, SearchServiceError
from ghostcite.logs import get_logger
from ghostcite.search.backends import (
    ResponseStore,
    Transport,
    TransportError,
    search_created_at,
)
from ghostcite.search.budget import Budget
from ghostcite.search.cache import cache_key
from ghostcite.search.ratelimit import RateLimiter
from ghostcite.search.sanitize import sanitize_response

_log = get_logger(__name__)
_BUDGET_EXHAUSTED = "The search budget for this run is used up."


class ResponseSource(StrEnum):
    """Where a response came from."""

    LIVE = "live"
    CACHE = "cache"
    MISS = "miss"
    """Offline or demo mode and nothing stored for this query."""


@dataclass(frozen=True, slots=True)
class SearchResponse:
    """The outcome of one search request."""

    params: Mapping[str, str]
    body: dict[str, Any] | None
    source: ResponseSource


@dataclass(slots=True)
class _Reservation:
    """Whether the request currently holds an unspent budget credit."""

    held: bool


class SearchClient:
    """Thread-safe entry point for every search GhostCite makes."""

    def __init__(
        self,
        store: ResponseStore,
        transport: Transport | None,
        budget: Budget,
        *,
        limiter: RateLimiter | None = None,
        cfg: SearchConfig = SEARCH,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._store = store
        self._transport = transport
        self._budget = budget
        self._limiter = limiter
        self._cfg = cfg
        self._sleep = sleep
        self._now = now
        self._rng = rng or random.Random()  # noqa: S311 - jitter, not cryptography
        self._lock = threading.Lock()
        self._live = 0
        self._credits = 0
        self._hits = 0
        self._inflight: dict[str, threading.Lock] = {}

    @property
    def offline(self) -> bool:
        """True when no live searches can be made (offline or demo mode)."""
        return self._transport is None

    @property
    def live_searches(self) -> int:
        """Live searches that returned an answer."""
        with self._lock:
            return self._live

    @property
    def credits_used(self) -> int:
        """Searches SerpApi may have billed: answered searches plus timed-out attempts."""
        with self._lock:
            return self._credits

    @property
    def cache_hits(self) -> int:
        """Requests answered from the cache or demo bundle."""
        with self._lock:
            return self._hits

    def is_cached(self, params: Mapping[str, str]) -> bool:
        """True when ``params`` would be answered without spending a credit."""
        return self._store.contains(params)

    def search(self, params: Mapping[str, str]) -> SearchResponse:
        """Answer ``params`` from the store, or with a live search if allowed.

        Identical requests are single-flight. When two references in one document plan
        the same query (the same paper cited twice with different years, say), the second
        request waits for the first and is answered from the cache. Two parallel misses
        would otherwise both pay for a live search.
        """
        with self._key_lock(params):
            return self._search_once(params)

    def _key_lock(self, params: Mapping[str, str]) -> threading.Lock:
        key = cache_key(params)
        with self._lock:
            return self._inflight.setdefault(key, threading.Lock())

    def _search_once(self, params: Mapping[str, str]) -> SearchResponse:
        cached = self._store.get(params)
        if cached is not None:
            with self._lock:
                self._hits += 1
            _log.debug("cache hit", extra={"engine": params.get("engine")})
            return SearchResponse(params, cached, ResponseSource.CACHE)
        if self._transport is None:
            return SearchResponse(params, None, ResponseSource.MISS)
        if not self._budget.reserve():
            raise BudgetExhaustedError(_BUDGET_EXHAUSTED)

        reservation = _Reservation(held=True)
        try:
            body = sanitize_response(self._fetch_with_retries(self._transport, params, reservation))
        finally:
            if reservation.held:
                self._budget.refund()  # the request failed without being billed
        self._store.put(params, body)
        with self._lock:
            self._live += 1
        _log.debug("live search", extra={"engine": params.get("engine")})
        return SearchResponse(params, body, ResponseSource.LIVE)

    def _spend(self, reservation: _Reservation) -> None:
        """Mark the held credit as billed."""
        reservation.held = False
        with self._lock:
            self._credits += 1

    def _backoff(self, attempt: int) -> float:
        """Full-jitter exponential backoff: uniform in [0, min(cap, base * 2**attempt)]."""
        ceiling = min(self._cfg.backoff_cap_seconds, self._cfg.backoff_base_seconds * 2**attempt)
        return self._rng.uniform(0.0, ceiling)

    def _fetch_with_retries(
        self, transport: Transport, params: Mapping[str, str], reservation: _Reservation
    ) -> dict[str, Any]:
        attempt = 0
        after_timeout = False
        while True:
            if self._limiter is not None:
                self._limiter.acquire()
            sent_at = self._now()
            try:
                body = transport.search(params)
            except TransportError as exc:
                attempt += 1
                if exc.maybe_charged:
                    self._spend(reservation)
                    after_timeout = True
                if not exc.retryable or attempt > self._cfg.max_retries:
                    raise SearchServiceError(
                        f"SerpApi request failed after {attempt} attempt(s): {exc.message}"
                    ) from None
                if not reservation.held:
                    if not self._budget.reserve():
                        raise BudgetExhaustedError(_BUDGET_EXHAUSTED) from None
                    reservation.held = True
                delay = self._backoff(attempt - 1)
                if exc.maybe_charged:
                    delay = max(delay, self._cfg.timeout_retry_delay_seconds)
                _log.warning(
                    "retrying search in %.1fs after: %s", delay, exc.message,
                    extra={"attempt": attempt},
                )  # fmt: skip
                self._sleep(delay)
                continue
            if after_timeout and self._served_from_serpapi_cache(body, sent_at):
                # The timed-out request finished on SerpApi's side and was billed there;
                # this identical retry was answered free from SerpApi's cache. The retry's
                # credit stays unspent and is refunded by search().
                _log.info("retry was served from SerpApi's cache; no extra credit used")
                return body
            self._spend(reservation)
            return body

    def _served_from_serpapi_cache(self, body: Mapping[str, Any], sent_at: datetime) -> bool:
        """True when the response was created well before this request was sent."""
        created = search_created_at(body)
        if created is None:
            return False
        margin = timedelta(seconds=self._cfg.cache_detection_margin_seconds)
        return created < sent_at - margin
