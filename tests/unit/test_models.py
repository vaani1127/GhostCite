from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ghostcite.models import (
    Author,
    Candidate,
    Engine,
    FieldMatch,
    FieldName,
    FieldStatus,
    MatchResult,
    ParseConfidence,
    ParsedFields,
    Reference,
    ReferenceResult,
    Report,
    RunMode,
    SourceFormat,
    Summary,
    Verdict,
)


def _reference() -> Reference:
    return Reference(
        index=1,
        raw="A. Vaswani et al. Attention is all you need. NeurIPS, 2017.",
        source_format=SourceFormat.TEXT,
        fields=ParsedFields(
            title="Attention is all you need",
            authors=(Author(surname="Vaswani", given="A."),),
            et_al=True,
            year=2017,
            venue="NeurIPS",
            confidence=ParseConfidence(title=0.9, authors=0.8, year=1.0, venue=0.6),
        ),
    )


def _match() -> MatchResult:
    candidate = Candidate(
        engine=Engine.GOOGLE_SCHOLAR,
        title="Attention is all you need",
        authors=("A Vaswani", "N Shazeer"),
        authors_truncated=True,
        year=2017,
        cited_by=100,
        query='"Attention is all you need"',
    )
    return MatchResult(
        candidate=candidate,
        fields=(
            FieldMatch(field=FieldName.TITLE, status=FieldStatus.MATCH, score=1.0),
            FieldMatch(field=FieldName.YEAR, status=FieldStatus.MATCH, score=1.0),
        ),
        confidence=0.95,
    )


def test_verdict_values_are_stable_strings() -> None:
    assert [v.value for v in Verdict] == [
        "VERIFIED",
        "METADATA_MISMATCH",
        "NOT_FOUND",
        "UNPARSEABLE",
        "SKIPPED_BUDGET",
    ]


def test_models_are_frozen() -> None:
    ref = _reference()
    with pytest.raises(ValidationError):
        ref.index = 2  # type: ignore[misc]


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Author(surname="Rao", nickname="x")  # type: ignore[call-arg]


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_confidence_bounds(bad: float) -> None:
    with pytest.raises(ValidationError):
        ParseConfidence(title=bad)


def test_reference_index_is_one_based() -> None:
    with pytest.raises(ValidationError):
        Reference(index=0, raw="x", source_format=SourceFormat.TEXT, fields=ParsedFields())


def test_empty_surname_rejected() -> None:
    with pytest.raises(ValidationError):
        Author(surname="")


def test_match_result_field_lookup() -> None:
    match = _match()
    title = match.field(FieldName.TITLE)
    assert title is not None
    assert title.status is FieldStatus.MATCH
    assert match.field(FieldName.VENUE) is None


def test_report_round_trips_through_json() -> None:
    result = ReferenceResult(
        reference=_reference(),
        verdict=Verdict.VERIFIED,
        confidence=0.95,
        reason="Title, authors and year match a Google Scholar record.",
        best_match=_match(),
        queries=('"Attention is all you need"',),
        searches_used=1,
    )
    report = Report(
        tool_version="0.1.0",
        generated_at=datetime(2026, 10, 9, tzinfo=UTC),
        source_name="paper.pdf",
        source_format=SourceFormat.PDF,
        mode=RunMode.LIVE,
        results=(result,),
        summary=Summary(
            total=1,
            counts={Verdict.VERIFIED: 1},
            integrity_score=100.0,
            checked=1,
            credits_used=1,
            cache_hits=0,
        ),
    )
    restored = Report.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.results[0].best_match is not None
