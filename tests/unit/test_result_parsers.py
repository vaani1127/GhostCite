from __future__ import annotations

from typing import Any

import pytest

from ghostcite.models import Engine
from ghostcite.search.parsers.google import clean_title, parse_google
from ghostcite.search.parsers.scholar import Summary, parse_scholar, parse_summary

ELLIPSIS = "\u2026"


def _summary(
    authors: tuple[str, ...] = (),
    venue: str | None = None,
    year: int | None = None,
    source: str | None = None,
    *,
    authors_cut: bool = False,
    venue_cut: bool = False,
) -> Summary:
    return Summary(authors, authors_cut, venue, venue_cut, year, source)


SUMMARIES = {
    "truncated": (
        f"A Vaswani, N Shazeer, N Parmar{ELLIPSIS} - Advances in neural {ELLIPSIS}, 2017"
        " - proceedings.neurips.cc",
        _summary(
            ("A Vaswani", "N Shazeer", "N Parmar"),
            "Advances in neural",
            2017,
            "proceedings.neurips.cc",
            authors_cut=True,
            venue_cut=True,
        ),
    ),
    "journal": (
        "Y LeCun, Y Bengio, G Hinton - nature, 2015 - nature.com",
        _summary(("Y LeCun", "Y Bengio", "G Hinton"), "nature", 2015, "nature.com"),
    ),
    "book_without_venue": (
        "I Goodfellow, Y Bengio, A Courville - 2016 - books.google.com",
        _summary(("I Goodfellow", "Y Bengio", "A Courville"), None, 2016, "books.google.com"),
    ),
    "dash_inside_venue": (
        "J Smith - Journal of A - B studies, 2010 - Elsevier",
        _summary(("J Smith",), "Journal of A - B studies", 2010, "Elsevier"),
    ),
    "venue_only": (
        "Advances in neural information processing systems, 2017",
        _summary((), "Advances in neural information processing systems", 2017),
    ),
    "authors_only": ("A Vaswani, N Shazeer", _summary(("A Vaswani", "N Shazeer"))),
    "authors_and_host": ("A Vaswani - arxiv.org", _summary(("A Vaswani",), source="arxiv.org")),
    "non_breaking_separators": (
        "A Kumar...\u00a0-\u00a0Indian J Med Res, 2019\u00a0-\u00a0ijmr.org.in",
        _summary(("A Kumar",), "Indian J Med Res", 2019, "ijmr.org.in", authors_cut=True),
    ),
    "empty": ("", _summary()),
}


@pytest.mark.parametrize(("summary", "expected"), SUMMARIES.values(), ids=SUMMARIES.keys())
def test_parse_summary(summary: str, expected: Summary) -> None:
    assert parse_summary(summary) == expected


def _scholar_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "position": 0,
        "title": "Attention is all you need",
        "result_id": "5Gohgn6QFikJ",
        "link": "https://proceedings.neurips.cc/paper/7181-attention-is-all-you-need",
        "snippet": "The dominant sequence transduction models ...",
        "publication_info": {
            "summary": "A Vaswani, N Shazeer - Advances in neural information processing "
            "systems, 2017 - proceedings.neurips.cc",
            "authors": [{"name": "A Vaswani", "author_id": "oR9sCGYAAAAJ"}],
        },
        "inline_links": {"cited_by": {"total": 150000, "cites_id": "2960712678066186980"}},
    }
    result.update(overrides)
    return result


def test_parse_scholar_builds_candidates() -> None:
    [candidate] = parse_scholar({"organic_results": [_scholar_result()]}, '"q"')
    assert candidate.engine is Engine.GOOGLE_SCHOLAR
    assert candidate.title == "Attention is all you need"
    assert candidate.authors == ("A Vaswani", "N Shazeer")
    assert candidate.year == 2017
    assert candidate.venue == "Advances in neural information processing systems"
    assert candidate.source == "proceedings.neurips.cc"
    assert candidate.cited_by == 150000
    assert candidate.result_id == "5Gohgn6QFikJ"
    assert candidate.query == '"q"'


def test_parse_scholar_is_defensive_about_odd_results() -> None:
    response = {
        "organic_results": [
            _scholar_result(title="[PDF] Tagged title of a paper"),
            _scholar_result(title=""),  # skipped
            "not an object",  # skipped
            _scholar_result(publication_info="oops", inline_links={"cited_by": {"total": "many"}}),
            _scholar_result(inline_links={"cited_by": {"total": True}}),
        ]
    }
    candidates = parse_scholar(response, "q")
    assert [c.title for c in candidates] == [
        "Tagged title of a paper",
        "Attention is all you need",
        "Attention is all you need",
    ]
    assert candidates[1].authors == ()
    assert candidates[1].cited_by is None
    assert candidates[2].cited_by is None


@pytest.mark.parametrize(
    "response",
    [
        {"error": "Google hasn't returned any results for this query."},
        {"organic_results": "not a list"},
        {},
    ],
)
def test_parse_scholar_empty(response: dict[str, Any]) -> None:
    assert parse_scholar(response, "q") == []


# A dash followed by more than four words is part of the title, not a site name.
LONG_TAIL = "Keeps - a dash when the tail is a long phrase of many words"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Wings of Fire - Wikipedia", "Wings of Fire"),
        ("Wings of Fire: An Autobiography | Amazon.in", "Wings of Fire: An Autobiography"),
        ("Deep Learning \u2013 MIT Press", "Deep Learning"),
        ("A very long title ...", "A very long title"),
        (LONG_TAIL, LONG_TAIL),
        ("Plain title", "Plain title"),
    ],
)
def test_google_clean_title(title: str, expected: str) -> None:
    assert clean_title(title) == expected


def test_parse_google_builds_capped_candidates() -> None:
    response = {
        "organic_results": [
            {
                "title": "Wings of Fire: An Autobiography - Google Books",
                "link": "https://books.google.com/books/about/Wings_of_Fire.html",
                "snippet": "A. P. J. Abdul Kalam ... Universities Press, 1999 - 180 pages",
                "source": "Google Books",
            },
            {
                "title": "Wings of Fire",
                "link": "https://en.wikipedia.org/wiki/Wings_of_Fire_(autobiography)",
                "date": "Mar 3, 2021",
                "snippet": "Published in 1999.",
            },
            {"title": "", "link": "https://example.org"},
            {"title": "No year here", "snippet": "Released in 2099 or so."},
        ]
    }
    candidates = parse_google(response, '"Wings of Fire" Kalam', current_year=2026)
    assert [c.title for c in candidates] == [
        "Wings of Fire: An Autobiography",
        "Wings of Fire",
        "No year here",
    ]
    assert all(c.engine is Engine.GOOGLE for c in candidates)
    assert [c.year for c in candidates] == [1999, 2021, None]
    assert [c.source for c in candidates] == ["Google Books", "en.wikipedia.org", None]
    assert candidates[0].authors == ()
    assert candidates[0].venue is None


def test_parse_google_empty() -> None:
    assert parse_google({"error": "Google hasn't returned any results for this query."}, "q") == []


def test_knowledge_graph_without_title_is_ignored() -> None:
    response = {"knowledge_graph": {"type": "Book"}, "organic_results": []}
    assert parse_google(response, "q") == []


def test_knowledge_graph_with_single_author_key_and_date() -> None:
    response = {
        "knowledge_graph": {"title": "Godan", "author": "Premchand", "publication_date": "1936"}
    }
    [graph] = parse_google(response, "q", current_year=2026)
    assert (graph.authors, graph.year, graph.link) == (("Premchand",), 1936, None)


BULLET = "\u2022"
BULLET_CASES = {
    "glued_without_names": (
        f"MK SurappaSadhana, 2003{BULLET}Springer",
        [],
        _summary(("MK Surappa",), "Sadhana", 2003, "Springer"),
    ),
    "year_glued_to_author": (
        f"J Bhagwati1993{BULLET}academic.oup.com",
        ["J Bhagwati"],
        _summary(("J Bhagwati",), None, 1993, "academic.oup.com"),
    ),
    "structured_names_win_over_camel_case": (
        f"Y LeCun, Y BengioNature, 2015{BULLET}nature.com",
        ["Y LeCun", "Y Bengio"],
        _summary(("Y LeCun", "Y Bengio"), "Nature", 2015, "nature.com"),
    ),
    "ellipses_on_both_sides": (
        f"A Vaswani, N Shazeer{ELLIPSIS}Advances in neural {ELLIPSIS}, 2017{BULLET}neurips.cc",
        [],
        _summary(
            ("A Vaswani", "N Shazeer"),
            "Advances in neural",
            2017,
            "neurips.cc",
            authors_cut=True,
            venue_cut=True,
        ),
    ),
    "no_junction": (
        f"lowercase only text{BULLET}example.org",
        [],
        _summary(("lowercase only text",), None, None, "example.org"),
    ),
}


@pytest.mark.parametrize(
    ("summary", "names", "expected"), BULLET_CASES.values(), ids=BULLET_CASES.keys()
)
def test_bullet_layout_summaries(summary: str, names: list[str], expected: Summary) -> None:
    assert parse_summary(summary, names) == expected
