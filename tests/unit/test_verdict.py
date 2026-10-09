from __future__ import annotations

import pytest

from ghostcite.match.score import match_candidate
from ghostcite.models import (
    Author,
    Candidate,
    Engine,
    FieldName,
    MatchResult,
    ParsedFields,
    Verdict,
)
from ghostcite.verdict.rules import decide, integrity_score, skipped, unparseable

FIELDS = ParsedFields(
    title="Attention is all you need",
    authors=(Author(surname="Vaswani"), Author(surname="Shazeer")),
    year=2017,
    venue="Advances in Neural Information Processing Systems",
)


def _match(fields: ParsedFields = FIELDS, **kwargs: object) -> MatchResult:
    candidate = Candidate.model_validate(
        {
            "engine": Engine.GOOGLE_SCHOLAR,
            "title": "Attention is all you need",
            "authors": ("A Vaswani", "N Shazeer", "N Parmar"),
            "authors_truncated": True,
            "year": 2017,
            "venue": "Advances in neural information processing systems",
            "cited_by": 274507,
            "query": "q",
            **kwargs,
        }
    )
    return match_candidate(fields, candidate)


def _decide(
    best: MatchResult | None, fields: ParsedFields = FIELDS, complete: bool = True
) -> object:
    return decide(fields, best, complete=complete, incomplete_reason="Budget ran out.")


def test_verified() -> None:
    decision = decide(FIELDS, _match(), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.VERIFIED
    assert decision.confidence == 1.0
    assert decision.reason == (
        "Title, authors, year and venue match a Google Scholar record (cited by 274,507)."
    )


def test_verified_with_preprint_year() -> None:
    decision = decide(FIELDS, _match(year=2018), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.VERIFIED
    assert "Scholar lists 2018, likely the preprint or published version" in decision.reason


def test_year_mismatch_reason_matches_the_spec_format() -> None:
    fields = FIELDS.model_copy(update={"year": 2021})
    decision = decide(fields, _match(fields, year=2019), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.METADATA_MISMATCH
    assert decision.reason == "Title matches, but year is 2019, not 2021."
    assert decision.mismatched == (FieldName.YEAR,)
    assert decision.confidence == 1.0


def test_several_mismatches_are_listed() -> None:
    fields = FIELDS.model_copy(
        update={
            "authors": (Author(surname="Hinton"), Author(surname="Bengio")),
            "year": 2015,
            "venue": "Journal of Imaginary Computing Letters",
        }
    )
    decision = decide(fields, _match(fields), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.METADATA_MISMATCH
    assert decision.mismatched == (FieldName.AUTHORS, FieldName.YEAR, FieldName.VENUE)
    assert decision.reason.startswith(
        "Title matches, but authors are A Vaswani, N Shazeer, N Parmar, not Hinton, Bengio;"
    )
    assert "year is 2017, not 2015" in decision.reason


def test_long_author_lists_are_shortened_in_reasons() -> None:
    fields = FIELDS.model_copy(
        update={"authors": tuple(Author(surname=f"Fake{c}") for c in "ABCDE")}
    )
    decision = decide(
        fields, _match(fields, authors_truncated=False), complete=True, incomplete_reason=""
    )
    assert "not FakeA, FakeB, FakeC et al." in decision.reason


def test_garbled_title_with_same_authors_and_year_is_a_mismatch() -> None:
    fields = FIELDS.model_copy(update={"title": "Attention is all we need, really"})
    decision = decide(fields, _match(fields), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.METADATA_MISMATCH
    assert decision.mismatched == (FieldName.TITLE,)
    assert "same authors and year but a different title" in decision.reason


def test_ambiguous_title_with_other_authors_is_not_found() -> None:
    fields = FIELDS.model_copy(
        update={
            "title": "Attention is all we need, really",
            "authors": (Author(surname="Raghunathan"),),
        }
    )
    decision = decide(fields, _match(fields), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.NOT_FOUND
    assert "closest result was “Attention is all you need”" in decision.reason
    assert 0.5 <= decision.confidence < 0.9


def test_nothing_found_at_all() -> None:
    decision = decide(FIELDS, None, complete=True, incomplete_reason="")
    assert (decision.verdict, decision.confidence) == (Verdict.NOT_FOUND, 0.9)
    assert decision.reason == "No Google Scholar record was found for this title."


def test_incomplete_search_is_skipped_not_condemned() -> None:
    decision = decide(FIELDS, None, complete=False, incomplete_reason="Budget ran out.")
    assert decision.verdict is Verdict.SKIPPED_BUDGET
    assert decision.reason == "Budget ran out."


def test_incomplete_search_still_verifies_a_found_paper() -> None:
    assert (
        decide(FIELDS, _match(), complete=False, incomplete_reason="x").verdict is Verdict.VERIFIED
    )


def test_google_only_match_is_capped_and_explained() -> None:
    book = FIELDS.model_copy(
        update={
            "title": "Wings of Fire: An Autobiography",
            "authors": (Author(surname="Abdul Kalam"),),
            "year": 1999,
            "venue": None,
        }
    )
    match = _match(
        book,
        engine=Engine.GOOGLE,
        title="Wings of Fire",
        authors=("A. P. J. Abdul Kalam",),
        authors_truncated=False,
        year=1999,
        venue=None,
        cited_by=None,
    )
    decision = decide(book, match, complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.VERIFIED
    assert decision.confidence <= 0.7
    assert "Found only via Google web search (not in Google Scholar)" in decision.reason
    assert "venue could not be confirmed" in decision.reason


def test_google_only_mismatch_is_capped() -> None:
    book = FIELDS.model_copy(update={"year": 1990})
    decision = decide(book, _match(book, engine=Engine.GOOGLE), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.METADATA_MISMATCH
    assert decision.confidence == 0.7


def test_title_only_verified_reason() -> None:
    fields = ParsedFields(title="Attention is all you need")
    decision = decide(fields, _match(fields), complete=True, incomplete_reason="")
    assert decision.reason.startswith("Title matches a Google Scholar record")


def test_unparseable_and_skipped_helpers() -> None:
    assert (
        decide(ParsedFields(), None, complete=True, incomplete_reason="").verdict
        is Verdict.UNPARSEABLE
    )
    assert "BibTeX entry" in unparseable(malformed_entry=True).reason
    assert skipped("why").confidence == 0.0


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({Verdict.VERIFIED: 8, Verdict.METADATA_MISMATCH: 2, Verdict.NOT_FOUND: 0}, 90.0),
        ({Verdict.VERIFIED: 1, Verdict.NOT_FOUND: 1, Verdict.SKIPPED_BUDGET: 9}, 50.0),
        ({Verdict.METADATA_MISMATCH: 1}, 50.0),
        ({Verdict.UNPARSEABLE: 3, Verdict.SKIPPED_BUDGET: 2}, None),
        ({}, None),
    ],
)
def test_integrity_score(counts: dict[Verdict, int], expected: float | None) -> None:
    assert integrity_score(counts) == expected
