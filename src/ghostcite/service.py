"""Wire a check run together for the CLI and the web UI.

``run_check`` chooses where responses come from:

* **live**: the local cache, then SerpApi. Before anything is spent, the free Account
  API confirms the account can afford the estimated searches (preflight), and its
  hourly limit sets the pacing.
* **offline**: the local cache only; no network, no key needed.
* **demo**: the committed demo bundle only, so judges can try GhostCite without a key.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ghostcite.config import SEARCH, SearchConfig
from ghostcite.credits import log_live_run
from ghostcite.document import Document
from ghostcite.errors import InputError
from ghostcite.models import Report, RunMode
from ghostcite.pipeline import ProgressCallback, check_document, dedupe_key
from ghostcite.samples import DEMO_BUNDLE, sample_path
from ghostcite.search.account import (
    AccountSource,
    check_quota,
    estimate_searches,
    fetch_quota,
    pacing_rate,
)
from ghostcite.search.backends import DemoBundle, LiveTransport, ResponseStore, Transport
from ghostcite.search.budget import Budget, CombinedBudget, SearchBudget
from ghostcite.search.cache import SqliteCache
from ghostcite.search.client import SearchClient
from ghostcite.search.planner import plan_queries
from ghostcite.search.ratelimit import RateLimiter
from ghostcite.settings import Settings

NO_KEY_MESSAGE = (
    "No SERPAPI_API_KEY is configured. Add it to a .env file (see .env.example), "
    "or try GhostCite without a key using --demo."
)


class AccountTransport(Transport, AccountSource, Protocol):
    """A transport that can also read the account quota (`LiveTransport` in production)."""


TransportFactory = Callable[[Settings, SearchConfig], AccountTransport]


def _live_transport(settings: Settings, cfg: SearchConfig) -> LiveTransport:
    if settings.api_key is None:
        raise InputError(NO_KEY_MESSAGE)
    return LiveTransport(settings.api_key, cfg.timeout_seconds)


@dataclass(frozen=True, slots=True)
class RunOptions:
    """How one check run may search."""

    mode: RunMode = RunMode.LIVE
    max_searches: int = SEARCH.default_max_searches
    concurrency: int = SEARCH.concurrency
    demo_bundle: Path | None = None
    """Override the demo bundle location (tests); defaults to the bundled samples."""
    surface: str = "cli"
    """Which front end started the run ("cli", "web", "eval"); recorded in the credits log."""


def uncached_references(document: Document, store: ResponseStore) -> int:
    """Unique references whose first planned query is not cached yet.

    This is what the preflight estimate is based on. Cached first queries usually
    resolve the reference for free.
    """
    seen: set[str] = set()
    count = 0
    for reference in document.references:
        key = dedupe_key(reference)
        if key in seen:
            continue
        seen.add(key)
        queries = plan_queries(reference.fields)
        if queries and not store.contains(queries[0].params):
            count += 1
    return count


def run_check(
    document: Document,
    settings: Settings,
    options: RunOptions,
    *,
    progress: ProgressCallback | None = None,
    shared_budget: Budget | None = None,
    transport_factory: TransportFactory = _live_transport,
    cfg: SearchConfig = SEARCH,
) -> Report:
    """Check ``document`` in the requested mode and return the report.

    ``shared_budget`` adds a cap that several runs share (the web UI's global budget) on
    top of this run's own ``max_searches``.
    """
    account_left: int | None = None
    with ExitStack() as stack:
        if options.mode is RunMode.DEMO:
            bundle_path = options.demo_bundle or sample_path(DEMO_BUNDLE)
            client = SearchClient(DemoBundle.load(bundle_path), None, SearchBudget(0), cfg=cfg)
        else:
            cache = stack.enter_context(
                SqliteCache(settings.cache_dir, cfg.cache_ttl_days * 86_400)
            )
            if options.mode is RunMode.OFFLINE:
                client = SearchClient(cache, None, SearchBudget(0), cfg=cfg)
            else:
                client, account_left = _live_client(
                    document, settings, options, cache, shared_budget, transport_factory, cfg
                )
        try:
            report = check_document(
                document,
                client,
                mode=options.mode,
                concurrency=options.concurrency,
                progress=progress,
            )
        finally:
            # Logged even when the run fails part-way, because searches may have been spent.
            if options.mode is RunMode.LIVE:
                log_live_run(
                    settings.credits_log,
                    surface=options.surface,
                    searches=client.credits_used,
                    references=len(document.references),
                    account_left=account_left,
                )
    return report


def _live_client(
    document: Document,
    settings: Settings,
    options: RunOptions,
    cache: SqliteCache,
    shared_budget: Budget | None,
    transport_factory: TransportFactory,
    cfg: SearchConfig,
) -> tuple[SearchClient, int | None]:
    """The live client, and the account's searches left when the Account API was asked."""
    transport = transport_factory(settings, cfg)
    limit = options.max_searches
    limiter = None
    account_left = None
    estimate = estimate_searches(uncached_references(document, cache), options.max_searches, cfg)
    if estimate > 0:
        quota = fetch_quota(transport)
        check_quota(quota, estimate)
        account_left = quota.searches_left
        limit = min(limit, quota.searches_left)
        rate = pacing_rate(quota, cfg)
        limiter = RateLimiter(rate) if rate else None
    budget: Budget = SearchBudget(limit)
    if shared_budget is not None:
        budget = CombinedBudget([budget, shared_budget])
    return SearchClient(cache, transport, budget, limiter=limiter, cfg=cfg), account_left
