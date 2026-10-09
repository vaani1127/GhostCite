"""Evaluation metrics: false alarms on real citations, detection of fabricated ones.

The two headline numbers answer the questions a reviewer asks:

* **False alarm rate**: of the real, correctly cited references, how many did GhostCite
  flag (NOT_FOUND or METADATA_MISMATCH)? Every false alarm costs a reviewer time and trust.
* **Detection rate**: of the fabricated or corrupted references, how many were flagged?

Exact-class precision, recall and F1 (for NOT_FOUND and METADATA_MISMATCH) and the full
confusion matrix follow. References GhostCite could not check (UNPARSEABLE, SKIPPED)
are counted and listed, never silently dropped.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ghostcite.evaluation.dataset import EvalRow, Kind, Perturbation
from ghostcite.models import Verdict

FLAGGED = frozenset({Verdict.NOT_FOUND, Verdict.METADATA_MISMATCH})
UNCHECKED = frozenset({Verdict.UNPARSEABLE, Verdict.SKIPPED_BUDGET})


@dataclass(frozen=True, slots=True)
class Outcome:
    """GhostCite's answer for one dataset row."""

    row: EvalRow
    verdict: Verdict
    confidence: float
    reason: str
    parsed_title: str | None
    best_title: str | None


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _prf(tp: int, fp: int, fn: int) -> dict[str, float | int | None]:
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    f1 = (
        round(2 * precision * recall / (precision + recall), 4)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def class_scores(outcomes: Sequence[Outcome], verdict: Verdict) -> dict[str, float | int | None]:
    """Precision, recall and F1 for one exact verdict class."""
    tp = sum(o.row.expected is verdict and o.verdict is verdict for o in outcomes)
    fp = sum(o.row.expected is not verdict and o.verdict is verdict for o in outcomes)
    fn = sum(o.row.expected is verdict and o.verdict is not verdict for o in outcomes)
    return _prf(tp, fp, fn)


def _headline(outcomes: Sequence[Outcome]) -> dict[str, Any]:
    real = [o for o in outcomes if o.row.kind is Kind.REAL]
    fake = [o for o in outcomes if o.row.kind is Kind.FABRICATED]
    flagged_real = sum(o.verdict in FLAGGED for o in real)
    flagged_fake = sum(o.verdict in FLAGGED for o in fake)
    return {
        "real": len(real),
        "fabricated": len(fake),
        "false_alarms": flagged_real,
        "false_alarm_rate": _rate(flagged_real, len(real)),
        "verified_real": sum(o.verdict is Verdict.VERIFIED for o in real),
        "unchecked_real": sum(o.verdict in UNCHECKED for o in real),
        "detected": flagged_fake,
        "detection_rate": _rate(flagged_fake, len(fake)),
        "unchecked_fabricated": sum(o.verdict in UNCHECKED for o in fake),
    }


def failures(outcomes: Sequence[Outcome]) -> list[dict[str, Any]]:
    """Every false alarm, missed fabrication and unchecked reference, with its reason."""
    rows = []
    for o in outcomes:
        if o.row.kind is Kind.REAL and o.verdict is not Verdict.VERIFIED:
            kind = "false alarm" if o.verdict in FLAGGED else "real reference not checked"
        elif o.row.kind is Kind.FABRICATED and o.verdict not in FLAGGED:
            kind = "missed fabrication"
        else:
            continue
        rows.append(
            {
                "id": o.row.id,
                "type": kind,
                "perturbation": o.row.perturbation.value if o.row.perturbation else None,
                "expected": o.row.expected.value,
                "verdict": o.verdict.value,
                "reason": o.reason,
                "parsed_title": o.parsed_title,
                "best_match": o.best_title,
            }
        )
    return rows


def class_differences(outcomes: Sequence[Outcome]) -> list[dict[str, str]]:
    """Fabrications that were flagged, but with a different verdict than expected."""
    return [
        {
            "id": o.row.id,
            "expected": o.row.expected.value,
            "verdict": o.verdict.value,
            "reason": o.reason,
        }
        for o in outcomes
        if o.row.kind is Kind.FABRICATED
        and o.verdict in FLAGGED
        and o.verdict is not o.row.expected
    ]


def summarize(outcomes: Sequence[Outcome]) -> dict[str, Any]:
    """All metrics for one run (one split, one input format)."""
    verdicts = [v.value for v in Verdict]
    expected = [Verdict.VERIFIED, Verdict.METADATA_MISMATCH, Verdict.NOT_FOUND]
    confusion = {
        e.value: {
            v: sum(o.row.expected is e and o.verdict.value == v for o in outcomes) for v in verdicts
        }
        for e in expected
    }
    per_type = {}
    for perturbation in Perturbation:
        group = [o for o in outcomes if o.row.perturbation is perturbation]
        detected = sum(o.verdict in FLAGGED for o in group)
        per_type[perturbation.value] = {
            "rows": len(group),
            "detected": detected,
            "detection_rate": _rate(detected, len(group)),
        }
    binary_tp = sum(o.row.kind is Kind.FABRICATED and o.verdict in FLAGGED for o in outcomes)
    binary_fp = sum(o.row.kind is Kind.REAL and o.verdict in FLAGGED for o in outcomes)
    binary_fn = sum(o.row.kind is Kind.FABRICATED and o.verdict not in FLAGGED for o in outcomes)
    return {
        "rows": len(outcomes),
        "headline": _headline(outcomes),
        "flagged_binary": _prf(binary_tp, binary_fp, binary_fn),
        "classes": {
            v.value: class_scores(outcomes, v)
            for v in (Verdict.NOT_FOUND, Verdict.METADATA_MISMATCH)
        },
        "confusion": confusion,
        "per_perturbation": per_type,
        "indian_subset": _headline([o for o in outcomes if o.row.indian]),
        "failures": failures(outcomes),
        "class_differences": class_differences(outcomes),
    }
