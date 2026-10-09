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


def test_reworded_title_of_a_real_paper_is_a_mismatch_not_verified() -> None:
    fields = FIELDS.model_copy(
        update={"title": "Attention is all we need for sequence transduction"}
    )
    decision = decide(fields, _match(fields), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.METADATA_MISMATCH
    assert decision.mismatched == (FieldName.TITLE,)
    assert decision.reason == (
        "Title differs from the closest real paper: 'Attention is all you need' (2017)."
    )


def test_one_word_substitution_is_never_verified() -> None:
    # Character similarity is exactly 0.90 here, but "we" replaced "you".
    fields = FIELDS.model_copy(update={"title": "Attention is all we need"})
    decision = decide(fields, _match(fields), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.METADATA_MISMATCH
    assert decision.reason.startswith("Title differs from the closest real paper")


def test_middle_band_tolerates_a_one_year_difference() -> None:
    fields = FIELDS.model_copy(update={"title": "Attention is all we need", "year": 2018})
    decision = decide(fields, _match(fields), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.METADATA_MISMATCH


@pytest.mark.parametrize(
    "update",
    [
        {"authors": (Author(surname="Raghunathan"),)},  # first author disagrees
        {"authors": (Author(surname="Shazeer"), Author(surname="Vaswani"))},  # wrong order
        {"year": 2021},  # year off by more than one
        {"authors": ()},  # nothing to confirm the first author
    ],
)
def test_middle_band_without_first_author_and_year_is_not_found(
    update: dict[str, object],
) -> None:
    fields = FIELDS.model_copy(
        update={"title": "Attention is all we need for sequence transduction", **update}
    )
    decision = decide(fields, _match(fields), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.NOT_FOUND
    assert "closest result was \u201cAttention is all you need\u201d" in decision.reason


def test_below_the_band_is_not_found_with_the_closest_candidate() -> None:
    fields = FIELDS.model_copy(update={"title": "Quantum gradient folding for citation graphs"})
    decision = decide(fields, _match(fields), complete=True, incomplete_reason="")
    assert decision.verdict is Verdict.NOT_FOUND
    assert "the closest result was" in decision.reason


def test_versions_note_for_year_or_venue_differences() -> None:
    fields = FIELDS.model_copy(update={"year": 2019})
    decision = decide(fields, _match(fields), complete=True, incomplete_reason="", versions=26)
    assert decision.reason == (
        "Title matches, but year is 2017, not 2019. "
        "(Google Scholar lists this work with 26 versions; this may be a different version.)"
    )


@pytest.mark.parametrize(
    ("update", "versions"),
    [
        ({"year": 2019}, 1),  # a single version: nothing to explain
        ({"year": 2019}, None),
        ({"authors": (Author(surname="Hinton"), Author(surname="Bengio"))}, 26),  # authors differ
    ],
)
def test_no_versions_note(update: dict[str, object], versions: int | None) -> None:
    fields = FIELDS.model_copy(update=update)
    decision = decide(
        fields, _match(fields), complete=True, incomplete_reason="", versions=versions
    )
    assert decision.verdict is Verdict.METADATA_MISMATCH
    assert "versions" not in decision.reason


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
