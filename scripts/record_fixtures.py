"""Record real SerpApi responses as sanitized test fixtures (spends at most 5 searches).

Usage::

    python scripts/record_fixtures.py

The queries are produced by GhostCite's own planner, so the fixtures exercise exactly the
requests the product makes. Responses go through the normal search client, which means
they are sanitized and cached, and a re-run within the cache TTL costs nothing. The free
Account API is read before and after the run (counts only), and every run is appended to
``.dev/credits.log``.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from ghostcite.config import SEARCH
from ghostcite.models import Author, ParsedFields
from ghostcite.search.account import AccountQuota, fetch_quota, pacing_rate
from ghostcite.search.backends import LiveTransport
from ghostcite.search.budget import SearchBudget
from ghostcite.search.cache import SqliteCache
from ghostcite.search.client import SearchClient
from ghostcite.search.planner import PlannedQuery, Strategy, plan_queries
from ghostcite.search.ratelimit import RateLimiter
from ghostcite.search.sanitize import sanitize_response
from ghostcite.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "serpapi"
CREDITS_LOG = ROOT / ".dev" / "credits.log"
MAX_SEARCHES = 5


def _pick(fields: ParsedFields, strategy: Strategy) -> PlannedQuery:
    return next(q for q in plan_queries(fields) if q.strategy is strategy)


# name -> (why it is useful, planned query)
FIXTURES: dict[str, tuple[str, PlannedQuery]] = {
    "scholar_exact_attention": (
        "Real, highly cited conference paper; exact-title strategy.",
        _pick(
            ParsedFields(
                title="Attention is all you need",
                authors=(Author(surname="Vaswani", given="A."),),
                year=2017,
                entry_type="inproceedings",
            ),
            Strategy.SCHOLAR_EXACT_TITLE,
        ),
    ),
    "scholar_exact_resnet": (
        "Real CVPR paper; exact-title strategy.",
        _pick(
            ParsedFields(
                title="Deep residual learning for image recognition",
                authors=(Author(surname="He", given="K."),),
                year=2016,
                entry_type="inproceedings",
            ),
            Strategy.SCHOLAR_EXACT_TITLE,
        ),
    ),
    "scholar_exact_fabricated": (
        "Invented title that should not exist; exact-title strategy.",
        _pick(
            ParsedFields(
                title="Quantum gradient folding for multilingual citation graphs",
                authors=(Author(surname="Raghunathan", given="P."),),
                year=2021,
                entry_type="article",
            ),
            Strategy.SCHOLAR_EXACT_TITLE,
        ),
    ),
    "scholar_title_author_perturbed": (
        "Real paper cited with a slightly wrong title; title + author strategy.",
        _pick(
            ParsedFields(
                title="Attention is all we need for sequence transduction",
                authors=(Author(surname="Vaswani", given="A."),),
                year=2017,
                entry_type="article",
            ),
            Strategy.SCHOLAR_TITLE_AUTHOR,
        ),
    ),
    "scholar_exact_versions": (
        "Paper published twice under one title (NeurIPS 2015 and IEEE TPAMI 2016); "
        "exact-title strategy.",
        _pick(
            ParsedFields(
                title="Faster R-CNN: Towards real-time object detection "
                "with region proposal networks",
                authors=(Author(surname="Ren", given="S."),),
                year=2016,
                entry_type="article",
            ),
            Strategy.SCHOLAR_EXACT_TITLE,
        ),
    ),
    "google_fallback_book": (
        "Indian autobiography (a book); Google web fallback strategy.",
        _pick(
            ParsedFields(
                title="Wings of Fire: An Autobiography",
                authors=(Author(surname="Abdul Kalam", given="A. P. J."),),
                year=1999,
                entry_type="book",
            ),
            Strategy.GOOGLE_FALLBACK,
        ),
    ),
}


def _log_credits(purpose: str, estimated: int, actual: int, before: int, after: int) -> None:
    CREDITS_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    line = (
        f"{stamp} | {purpose} | estimated={estimated} | actual={actual} "
        f"| account_left_before={before} | account_left_after={after}\n"
    )
    with CREDITS_LOG.open("a", encoding="utf-8") as log:
        log.write(line)


def main() -> int:
    settings = load_settings()
    if settings.api_key is None:
        print("SERPAPI_API_KEY is not set. Add it to .env (see .env.example) and re-run.")
        return 2
    transport = LiveTransport(settings.api_key, SEARCH.timeout_seconds)
    before: AccountQuota = fetch_quota(transport)
    print(f"Account: {before.searches_left} searches left, hourly limit {before.hourly_limit}.")

    with SqliteCache(settings.cache_dir, SEARCH.cache_ttl_days * 86400) as cache:
        uncached = [name for name, (_, q) in FIXTURES.items() if not cache.contains(q.params)]
        estimated = len(uncached)
        print(f"Planned: {len(FIXTURES)} queries, {estimated} not cached (each costs 1 search).")
        if estimated > before.searches_left:
            print("Not enough searches left on the account; nothing was spent.")
            return 3
        rate = pacing_rate(before)
        client = SearchClient(
            cache,
            transport,
            SearchBudget(MAX_SEARCHES),
            limiter=RateLimiter(rate) if rate else None,
        )
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        for name, (description, query) in FIXTURES.items():
            response = client.search(query.params)
            fixture = {
                "description": description,
                "strategy": query.strategy.value,
                "params": query.params,
                "response": sanitize_response(response.body),
            }
            path = FIXTURE_DIR / f"{name}.json"
            path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", "utf-8")
            print(f"  {name}: {response.source.value} -> {path.relative_to(ROOT)}")

    after = fetch_quota(transport)
    _log_credits(
        "Checkpoint 3 live smoke test (record fixtures)",
        estimated,
        client.credits_used,
        before.searches_left,
        after.searches_left,
    )
    print(f"Credits used: {client.credits_used}. Account now: {after.searches_left} left.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
