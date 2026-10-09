"""Parsers against real, sanitized SerpApi responses recorded by scripts/record_fixtures.py."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ghostcite.models import Author, Engine, ParsedFields
from ghostcite.search.parsers.google import parse_google
from ghostcite.search.parsers.scholar import parse_scholar
from ghostcite.search.planner import Strategy, plan_queries
from tests.conftest import FIXTURES

SERPAPI = FIXTURES / "serpapi"


def _fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SERPAPI / f"{name}.json").read_text(encoding="utf-8"))
    return data


def test_every_fixture_documents_its_request() -> None:
    names = sorted(path.stem for path in SERPAPI.glob("*.json"))
    assert names == [
        "google_fallback_book",
        "scholar_exact_attention",
        "scholar_exact_fabricated",
        "scholar_exact_resnet",
        "scholar_exact_versions",
        "scholar_title_author_perturbed",
    ]
    for name in names:
        fixture = _fixture(name)
        assert {"description", "strategy", "params", "response"} <= fixture.keys()
        assert fixture["response"]["search_metadata"]["status"] == "Success"
        assert fixture["response"]["search_parameters"]["q"] == fixture["params"]["q"]


def test_real_paper_is_the_top_scholar_result() -> None:
    fixture = _fixture("scholar_exact_attention")
    candidates = parse_scholar(fixture["response"], fixture["params"]["q"])
    assert len(candidates) == 10
    top = candidates[0]
    assert top.engine is Engine.GOOGLE_SCHOLAR
    assert top.title == "Attention is all you need"
    assert top.authors == ("A Vaswani", "N Shazeer", "N Parmar")
    assert top.authors_truncated
    assert top.year == 2017
    assert top.venue == "Advances in neural"
    assert top.venue_truncated
    assert top.source == "proceedings.neurips.cc"
    assert top.cited_by is not None
    assert top.cited_by > 100_000


def test_leading_venue_ellipsis_is_stripped() -> None:
    fixture = _fixture("scholar_exact_resnet")
    top = parse_scholar(fixture["response"], fixture["params"]["q"])[0]
    assert top.title == "Deep residual learning for image recognition"
    assert top.authors == ("K He", "X Zhang", "S Ren", "J Sun")
    assert top.venue == "of the IEEE conference on computer"
    assert top.venue_truncated
    assert top.year == 2016


def test_fabricated_title_returns_no_candidates() -> None:
    fixture = _fixture("scholar_exact_fabricated")
    response = fixture["response"]
    assert "hasn't returned any results" in response["error"]
    assert parse_scholar(response, fixture["params"]["q"]) == []


def test_title_author_strategy_recovers_a_misquoted_title() -> None:
    fixture = _fixture("scholar_title_author_perturbed")
    candidates = parse_scholar(fixture["response"], fixture["params"]["q"])
    assert candidates[0].title == "Attention is all you need"
    # A two-segment summary ("authors - venue, year") without a source host.
    notes = candidates[1]
    assert notes.year == 2023
    assert notes.source is None


def test_google_fallback_uses_the_knowledge_graph() -> None:
    fixture = _fixture("google_fallback_book")
    assert fixture["params"]["gl"] == "in"
    candidates = parse_google(fixture["response"], fixture["params"]["q"], current_year=2026)
    graph = candidates[0]
    assert graph.source == "Google Knowledge Graph"
    assert graph.title == "Wings of Fire"
    assert graph.authors == ("A. P. J. Abdul Kalam", "Arun Tiwari")
    assert graph.year == 1999
    assert len(candidates) > 1
    assert all(c.engine is Engine.GOOGLE for c in candidates)


@pytest.mark.parametrize(
    ("name", "fields", "strategy"),
    [
        (
            "scholar_exact_attention",
            ParsedFields(title="Attention is all you need", authors=(Author(surname="Vaswani"),)),
            Strategy.SCHOLAR_EXACT_TITLE,
        ),
        (
            "google_fallback_book",
            ParsedFields(
                title="Wings of Fire: An Autobiography",
                authors=(Author(surname="Abdul Kalam"),),
                entry_type="book",
            ),
            Strategy.GOOGLE_FALLBACK,
        ),
    ],
)
def test_fixtures_match_what_the_planner_sends_today(
    name: str, fields: ParsedFields, strategy: Strategy
) -> None:
    planned = next(q for q in plan_queries(fields) if q.strategy is strategy)
    assert planned.params == _fixture(name)["params"]
