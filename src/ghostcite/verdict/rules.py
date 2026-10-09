"""Deterministic rules that turn match evidence into a verdict and a one-line reason.

The rules, in order:

1. No usable title                                     -> UNPARSEABLE (nothing searched)
2. Title matches (same words, similarity >= title_match),
   no field disagrees on the best-agreeing version     -> VERIFIED
3. Title matches, some field disagrees                 -> METADATA_MISMATCH
   (with a note when Scholar lists several versions and only year/venue differ)
4. Middle band: the title is a reworded version of a real paper's
   (overlap >= title_reject) and the first author and year (+-1) agree
                                                       -> METADATA_MISMATCH ("Title differs ...")
5. Otherwise, all planned searches ran                  -> NOT_FOUND (closest candidate shown)
6. Otherwise (budget ran out, or offline cache miss)    -> SKIPPED_BUDGET

Thresholds are never relaxed to verify a reworded title: a slightly changed title of
a real paper is a classic hallucination signature, so it lands in rule 4 or 5.

The same evidence always produces the same verdict and reason. No model is involved.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ghostcite.config import MATCH, SCORE, VERDICT, MatchConfig, ScoreConfig, VerdictConfig
from ghostcite.match.score import in_middle_band, title_status
from ghostcite.models import (
    Engine,
    FieldMatch,
    FieldName,
    FieldStatus,
    MatchResult,
    ParsedFields,
    Verdict,
)

_JUDGED_FIELDS = (FieldName.AUTHORS, FieldName.YEAR, FieldName.VENUE)
_VERSION_FIELDS = (FieldName.YEAR, FieldName.VENUE)
"""Fields that legitimately differ between versions of one work (preprint vs journal)."""
_MAX_NAMES_SHOWN = 3


@dataclass(frozen=True, slots=True)
class Decision:
    """A verdict with its confidence, reason and the fields that disagree."""

    verdict: Verdict
    confidence: float
    reason: str
    mismatched: tuple[FieldName, ...] = ()


def unparseable(*, malformed_entry: bool = False) -> Decision:
    """Verdict for a reference without a usable title."""
    reason = (
        "The BibTeX entry could not be parsed, so it was not searched."
        if malformed_entry
        else "No title could be extracted from this reference, so it was not searched."
    )
    return Decision(Verdict.UNPARSEABLE, 1.0, reason)


def skipped(reason: str) -> Decision:
    """Verdict for a reference that could not be fully checked."""
    return Decision(Verdict.SKIPPED_BUDGET, 0.0, reason)


def _title_score(match: MatchResult) -> float:
    field = match.field(FieldName.TITLE)
    return field.score if field is not None and field.score is not None else 0.0


def _status(match: MatchResult, name: FieldName) -> FieldStatus:
    field = match.field(name)
    return field.status if field is not None else FieldStatus.UNKNOWN


def _shorten(names: str | None) -> str:
    parts = [p.strip() for p in (names or "").split(",") if p.strip()]
    shown = ", ".join(parts[:_MAX_NAMES_SHOWN])
    return f"{shown} et al." if len(parts) > _MAX_NAMES_SHOWN else shown


def _difference(field: FieldMatch) -> str:
    if field.field is FieldName.AUTHORS:
        return f"authors are {_shorten(field.found)}, not {_shorten(field.cited)}"
    return f"{field.field.value} is {field.found}, not {field.cited}"


def _join(words: Sequence[str]) -> str:
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} and {words[-1]}"


def _verified_reason(match: MatchResult) -> str:
    agreeing = ["title"] + [
        name.value
        for name in _JUDGED_FIELDS
        if _status(match, name) in (FieldStatus.MATCH, FieldStatus.PARTIAL)
    ]
    subject = _join(agreeing).capitalize()
    verb = "matches" if len(agreeing) == 1 else "match"
    candidate = match.candidate
    if candidate.engine is Engine.GOOGLE:
        unconfirmed = [
            name.value
            for name in (FieldName.AUTHORS, FieldName.VENUE)
            if _status(match, name) is FieldStatus.UNKNOWN
        ]
        reason = (
            f"{subject} {verb} a Google web result. "
            "Found only via Google web search (not in Google Scholar)"
        )
        if unconfirmed:
            reason += f"; {_join(unconfirmed)} could not be confirmed"
        return reason + "."
    reason = f"{subject} {verb} a Google Scholar record"
    if candidate.cited_by:
        reason += f" (cited by {candidate.cited_by:,})"
    if _status(match, FieldName.YEAR) is FieldStatus.PARTIAL:
        year = match.field(FieldName.YEAR)
        found = year.found if year is not None else "?"
        reason += f"; Scholar lists {found}, likely the preprint or published version"
    return reason + "."


def decide(
    fields: ParsedFields,
    best: MatchResult | None,
    *,
    complete: bool,
    incomplete_reason: str,
    versions: int | None = None,
    match_cfg: MatchConfig = MATCH,
    cfg: VerdictConfig = VERDICT,
) -> Decision:
    """Apply the rules above to the best candidate found for a reference.

    ``versions`` is the largest version count Scholar reports for any title-matching
    candidate. It only adds a note to year/venue mismatches.
    """
    if not fields.title:
        return unparseable()
    title = _title_score(best) if best is not None else 0.0

    if best is not None and title_status(best) is FieldStatus.MATCH:
        differences = [
            f
            for name in _JUDGED_FIELDS
            if (f := best.field(name)) and f.status is FieldStatus.MISMATCH
        ]
        if not differences:
            return Decision(Verdict.VERIFIED, best.confidence, _verified_reason(best))
        confidence = (
            min(title, match_cfg.fallback_confidence_cap)
            if best.candidate.engine is Engine.GOOGLE
            else title
        )
        reason = "Title matches, but " + "; ".join(_difference(f) for f in differences) + "."
        if versions and versions > 1 and all(f.field in _VERSION_FIELDS for f in differences):
            reason += (
                f" (Google Scholar lists this work with {versions} versions; "
                "this may be a different version.)"
            )
        return Decision(
            Verdict.METADATA_MISMATCH,
            round(confidence, 4),
            reason,
            tuple(f.field for f in differences),
        )

    if best is not None and in_middle_band(best, fields, match_cfg):
        candidate = best.candidate
        reason = (
            f"Title differs from the closest real paper: '{candidate.title}' ({candidate.year})."
        )
        return Decision(Verdict.METADATA_MISMATCH, best.confidence, reason, (FieldName.TITLE,))

    if not complete:
        return skipped(incomplete_reason)

    if best is None:
        return Decision(
            Verdict.NOT_FOUND,
            cfg.not_found_confidence,
            "No Google Scholar record was found for this title.",
        )
    confidence = max(cfg.not_found_floor, cfg.not_found_confidence - title / 2)
    reason = (
        "No Google Scholar record matches this title; the closest result was "
        f"\u201c{best.candidate.title}\u201d ({round(title * 100)}% similar)."
    )
    return Decision(Verdict.NOT_FOUND, round(confidence, 4), reason)


def integrity_score(counts: Mapping[Verdict, int], cfg: ScoreConfig = SCORE) -> float | None:
    """Share of checkable references that are sound, as a percentage.

    ``100 * (verified + mismatch_weight * mismatched) / (verified + mismatched + not_found)``.
    UNPARSEABLE and SKIPPED_BUDGET references are excluded, because nothing was learned
    about them. Returns ``None`` when no reference was checkable.
    """
    verified = counts.get(Verdict.VERIFIED, 0)
    mismatched = counts.get(Verdict.METADATA_MISMATCH, 0)
    checked = verified + mismatched + counts.get(Verdict.NOT_FOUND, 0)
    if checked == 0:
        return None
    return round(100 * (verified + cfg.mismatch_weight * mismatched) / checked, 1)
