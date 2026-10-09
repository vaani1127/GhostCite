from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import SecretStr

from ghostcite.config import SearchConfig
from ghostcite.document import load_text
from ghostcite.errors import InputError, InsufficientCreditsError
from ghostcite.models import RunMode, Verdict
from ghostcite.search.budget import SearchBudget
from ghostcite.search.cache import SqliteCache
from ghostcite.service import (
    NO_KEY_MESSAGE,
    RunOptions,
    TransportFactory,
    run_check,
    uncached_references,
)
from ghostcite.settings import Settings
from tests.helpers import (
    ATTENTION,
    FABRICATED,
    RESNET,
    FixtureTransport,
    demo_bundle_payload,
    numbered,
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(api_key=SecretStr("test-key-not-real"), cache_dir=tmp_path / "cache")


def _factory(transport: FixtureTransport) -> TransportFactory:
    def build(settings: Settings, cfg: SearchConfig) -> FixtureTransport:
        return transport

    return build


def test_live_run_checks_quota_and_paces(settings: Settings) -> None:
    transport = FixtureTransport()
    document = load_text(numbered(ATTENTION, RESNET))
    report = run_check(document, settings, RunOptions(), transport_factory=_factory(transport))
    assert [r.verdict for r in report.results] == [Verdict.VERIFIED, Verdict.VERIFIED]
    assert transport.account_calls == 1
    assert report.mode is RunMode.LIVE


def test_preflight_refuses_before_spending(settings: Settings) -> None:
    transport = FixtureTransport()
    transport.searches_left = 1
    document = load_text(numbered(ATTENTION, RESNET, FABRICATED))
    with pytest.raises(InsufficientCreditsError, match="needs about 5 searches"):
        run_check(document, settings, RunOptions(), transport_factory=_factory(transport))
    assert transport.calls == []


def test_budget_is_clamped_to_what_the_account_has(settings: Settings) -> None:
    transport = FixtureTransport()
    transport.searches_left = 2
    document = load_text(numbered(ATTENTION))
    report = run_check(
        document, settings, RunOptions(max_searches=50), transport_factory=_factory(transport)
    )
    assert report.results[0].verdict is Verdict.VERIFIED


def test_fully_cached_runs_skip_the_account_api(settings: Settings) -> None:
    document = load_text(numbered(ATTENTION))
    first = FixtureTransport()
    run_check(document, settings, RunOptions(), transport_factory=_factory(first))
    second = FixtureTransport()
    report = run_check(document, settings, RunOptions(), transport_factory=_factory(second))
    assert (second.account_calls, second.calls) == (0, [])
    assert report.summary.cache_hits == 1


def test_shared_budget_caps_several_runs(settings: Settings) -> None:
    shared = SearchBudget(1)
    document = load_text(numbered(ATTENTION, RESNET))
    report = run_check(
        document,
        settings,
        RunOptions(concurrency=1),
        shared_budget=shared,
        transport_factory=_factory(FixtureTransport()),
    )
    assert sorted(r.verdict for r in report.results) == [Verdict.SKIPPED_BUDGET, Verdict.VERIFIED]
    assert shared.used == 1


def test_live_mode_without_key_points_to_demo(tmp_path: Path) -> None:
    no_key = Settings(api_key=None, cache_dir=tmp_path)
    with pytest.raises(InputError) as exc:
        run_check(load_text(numbered(ATTENTION)), no_key, RunOptions())
    assert exc.value.message == NO_KEY_MESSAGE
    assert "--demo" in NO_KEY_MESSAGE


def test_live_mode_builds_the_real_transport(settings: Settings) -> None:
    # The cache is warmed first, so the real transport is built but never used.
    document = load_text(numbered(ATTENTION))
    run_check(document, settings, RunOptions(), transport_factory=_factory(FixtureTransport()))
    report = run_check(document, settings, RunOptions())
    assert report.summary.credits_used == 0


def test_offline_mode_never_needs_a_key(tmp_path: Path) -> None:
    no_key = Settings(api_key=None, cache_dir=tmp_path)
    report = run_check(load_text(numbered(ATTENTION)), no_key, RunOptions(mode=RunMode.OFFLINE))
    assert report.results[0].verdict is Verdict.SKIPPED_BUDGET


def test_demo_mode_reads_the_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps(demo_bundle_payload()), "utf-8")
    no_key = Settings(api_key=None, cache_dir=tmp_path / "cache")
    report = run_check(
        load_text(numbered(ATTENTION)), no_key, RunOptions(mode=RunMode.DEMO, demo_bundle=bundle)
    )
    assert report.results[0].verdict is Verdict.VERIFIED
    assert report.mode is RunMode.DEMO
    assert not (tmp_path / "cache").exists()  # demo mode never touches the cache


def test_uncached_references_counts_unique_first_queries(settings: Settings) -> None:
    document = load_text(numbered(ATTENTION, ATTENTION, RESNET, "Smith J. 2010."))
    with SqliteCache(settings.cache_dir, 3600) as cache:
        assert uncached_references(document, cache) == 2
