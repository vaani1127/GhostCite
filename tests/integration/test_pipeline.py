"""The whole pipeline against real recorded SerpApi responses (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostcite.document import load_document, load_text
from ghostcite.errors import SearchServiceError
from ghostcite.models import RunMode, Verdict
from ghostcite.pipeline import Progress, check_document, dedupe_key
from ghostcite.search.backends import DemoBundle
from ghostcite.search.budget import SearchBudget
from ghostcite.search.cache import SqliteCache
from ghostcite.search.client import SearchClient
from tests.conftest import FIXTURES
from tests.helpers import (
    ATTENTION,
    BOOK,
    FABRICATED,
    RESNET,
    WRONG_YEAR,
    FixtureTransport,
    numbered,
    recorded_responses,
)


@pytest.fixture
def cache(tmp_path: Path) -> SqliteCache:
    return SqliteCache(tmp_path / "cache", ttl_seconds=3600)


def _live(cache: SqliteCache, transport: FixtureTransport, budget: int = 50) -> SearchClient:
    return SearchClient(cache, transport, SearchBudget(budget))


def test_live_run_gives_the_expected_verdicts(cache: SqliteCache) -> None:
    document = load_text(numbered(ATTENTION, RESNET, WRONG_YEAR, FABRICATED, BOOK))
    transport = FixtureTransport()
    report = check_document(document, _live(cache, transport), mode=RunMode.LIVE)

    verdicts = [r.verdict for r in report.results]
    assert verdicts == [
        Verdict.VERIFIED,
        Verdict.VERIFIED,
        Verdict.METADATA_MISMATCH,
        Verdict.NOT_FOUND,
        Verdict.VERIFIED,
    ]
    wrong_year = report.results[2]
    assert wrong_year.reason == "Title matches, but year is 2017, not 2019."
    assert wrong_year.best_match is not None
    assert wrong_year.best_match.candidate.cited_by == 274507
    book = report.results[4]
    assert book.confidence <= 0.7
    assert "Google web search" in book.reason

    # 1 + 1 + 0 (identical first query, served from GhostCite's cache) + 2 + 3 live calls.
    assert len(transport.calls) == 7
    assert report.summary.credits_used == 7
    assert report.summary.counts[Verdict.VERIFIED] == 3
    assert report.summary.integrity_score == pytest.approx(70.0)


def test_search_stops_at_the_first_title_match(cache: SqliteCache) -> None:
    transport = FixtureTransport()
    report = check_document(load_text(ATTENTION), _live(cache, transport), mode=RunMode.LIVE)
    assert len(transport.calls) == 1
    assert report.results[0].searches_used == 1
    assert report.results[0].queries == ('"Attention is all you need"',)


def test_duplicates_are_searched_once(cache: SqliteCache) -> None:
    text = numbered(ATTENTION, RESNET, ATTENTION)
    transport = FixtureTransport()
    report = check_document(load_text(text), _live(cache, transport), mode=RunMode.LIVE)
    duplicate = report.results[2]
    assert duplicate.duplicate_of == 1
    assert duplicate.searches_used == 0
    assert duplicate.reason.startswith("Duplicate of reference 1. ")
    assert duplicate.reference.index == 3
    assert len(transport.calls) == 2


def test_budget_exhaustion_skips_cleanly(cache: SqliteCache) -> None:
    document = load_text(numbered(ATTENTION, RESNET, FABRICATED))
    report = check_document(
        document, _live(cache, FixtureTransport(), budget=1), mode=RunMode.LIVE, concurrency=1
    )
    verdicts = [r.verdict for r in report.results]
    assert verdicts.count(Verdict.VERIFIED) == 1
    assert verdicts.count(Verdict.SKIPPED_BUDGET) == 2
    skipped = next(r for r in report.results if r.verdict is Verdict.SKIPPED_BUDGET)
    assert "search budget" in skipped.reason
    assert report.summary.credits_used == 1


def test_cached_references_are_checked_even_after_the_budget_is_gone(cache: SqliteCache) -> None:
    check_document(load_text(ATTENTION), _live(cache, FixtureTransport()), mode=RunMode.LIVE)
    document = load_text(numbered(ATTENTION, RESNET))
    report = check_document(document, _live(cache, FixtureTransport(), budget=0), mode=RunMode.LIVE)
    assert [r.verdict for r in report.results] == [Verdict.VERIFIED, Verdict.SKIPPED_BUDGET]
    assert report.summary.cache_hits == 1


def test_offline_mode_uses_only_the_cache(cache: SqliteCache) -> None:
    check_document(load_text(ATTENTION), _live(cache, FixtureTransport()), mode=RunMode.LIVE)
    client = SearchClient(cache, None, SearchBudget(0))
    report = check_document(load_text(numbered(ATTENTION, RESNET)), client, mode=RunMode.OFFLINE)
    assert report.results[0].verdict is Verdict.VERIFIED
    assert report.results[1].verdict is Verdict.SKIPPED_BUDGET
    assert "offline mode" in report.results[1].reason
    assert report.summary.credits_used == 0


def test_demo_mode_with_a_bundle() -> None:
    client = SearchClient(DemoBundle(recorded_responses()), None, SearchBudget(0))
    report = check_document(
        load_text(numbered(ATTENTION, BOOK, FABRICATED)), client, mode=RunMode.DEMO
    )
    verdicts = [r.verdict for r in report.results]
    assert verdicts[:2] == [Verdict.VERIFIED, Verdict.VERIFIED]
    # Only the first of the fabricated reference's two queries is in the bundle.
    assert verdicts[2] is Verdict.SKIPPED_BUDGET
    assert "demo data" in report.results[2].reason


def test_bibtex_document_with_unparseable_entry(cache: SqliteCache) -> None:
    data = (FIXTURES / "bib" / "mixed.bib").read_bytes()
    document = load_document(data, "mixed.bib")
    report = check_document(document, _live(cache, FixtureTransport()), mode=RunMode.LIVE)
    broken = next(r for r in report.results if r.reference.key == "broken2019")
    assert broken.verdict is Verdict.UNPARSEABLE
    assert "BibTeX entry could not be parsed" in broken.reason
    assert broken.searches_used == 0
    assert report.warnings == document.warnings


def test_fatal_errors_abort_the_run(cache: SqliteCache) -> None:
    class RejectingTransport(FixtureTransport):
        def search(self, params: object) -> dict[str, object]:
            raise SearchServiceError("SerpApi rejected the API key (HTTP 401).")

    with pytest.raises(SearchServiceError, match="rejected"):
        check_document(
            load_text(numbered(ATTENTION, RESNET)),
            _live(cache, RejectingTransport()),
            mode=RunMode.LIVE,
        )


def test_progress_is_reported_for_every_reference(cache: SqliteCache) -> None:
    events: list[Progress] = []
    text = numbered(ATTENTION, RESNET, ATTENTION)
    check_document(
        load_text(text), _live(cache, FixtureTransport()), mode=RunMode.LIVE, progress=events.append
    )
    assert sorted(e.done for e in events) == [1, 2, 3]
    assert {e.total for e in events} == {3}


def test_dedupe_key_for_untitled_references() -> None:
    document = load_text("[1] Smith J. 2010.\n[2] Smith J. 2010.")
    keys = {dedupe_key(r) for r in document.references}
    assert len(keys) == 1
    assert next(iter(keys)).startswith("raw:")
