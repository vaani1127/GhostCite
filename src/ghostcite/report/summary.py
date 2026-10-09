"""Presentation helpers shared by the Markdown, HTML and terminal renderers."""

from __future__ import annotations

from ghostcite.models import ReferenceResult, Report, Verdict

VERDICT_LABELS: dict[Verdict, str] = {
    Verdict.VERIFIED: "Verified",
    Verdict.METADATA_MISMATCH: "Metadata mismatch",
    Verdict.NOT_FOUND: "Not found",
    Verdict.UNPARSEABLE: "Unparseable",
    Verdict.SKIPPED_BUDGET: "Skipped",
}

SCORE_FORMULA = (
    "Integrity score = 100 x (verified + 0.5 x mismatched) / (verified + mismatched + not found). "
    "Unparseable and skipped references are excluded."
)


def cited_title(result: ReferenceResult) -> str:
    """The title as cited, or the start of the raw reference when none was parsed."""
    title = result.reference.fields.title
    if title:
        return title
    raw = result.reference.raw
    return raw if len(raw) <= 80 else raw[:77] + "..."


def score_text(report: Report) -> str:
    """Human-readable integrity score, e.g. ``"86.5 / 100"``."""
    score = report.summary.integrity_score
    return "n/a" if score is None else f"{score:g} / 100"


def problem_count(report: Report) -> int:
    """References that need attention: not found or with wrong metadata."""
    counts = report.summary.counts
    return counts.get(Verdict.NOT_FOUND, 0) + counts.get(Verdict.METADATA_MISMATCH, 0)
