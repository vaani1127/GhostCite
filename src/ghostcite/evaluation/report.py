"""Markdown rendering of evaluation results (``eval/results*.md``).

Every rate is shown with its counts and a 95% Wilson score interval, because the sets
are small. Per-type rates are not shown below ``MIN_RATE_N`` rows: the counts say more.
"""

from __future__ import annotations

import math
from typing import Any

MIN_RATE_N = 5
"""Below this many rows, show counts only: a percentage would suggest false precision."""
_Z95 = 1.959964

HELD_OUT_NOTE = (
    "**This is the held-out estimate**: the first and only run on the test split made "
    "before any change informed by it. Quote these test-split numbers."
)
POST_FIX_NOTE = (
    "**Post-fix rerun, not a held-out estimate.** Bugs found while reading the first "
    "test-split run were fixed before this run, so its test-split numbers are optimistic. "
    "Quote `eval/results_heldout_first_run.md` instead; docs/EVALUATION.md explains both."
)
HELD_OUT_V2_NOTE = (
    "**Frozen held-out set v2 (headline result).** The dataset shares no paper with v1, "
    "was frozen (SHA-256 in docs/EVALUATION.md) before any search, and was run exactly "
    "once with the code frozen. No code was changed in response to these results."
)
_PART_LABELS = {"v2": "Held-out v2", "test": "Test split", "tuning": "Tuning split"}


def wilson(successes: int, n: int) -> tuple[float, float] | None:
    """95% Wilson score interval for ``successes`` out of ``n`` (``None`` when n is 0)."""
    if n <= 0:
        return None
    p = successes / n
    z2 = _Z95 * _Z95
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = _Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def rate_text(successes: int, n: int, *, min_n: int = 0) -> str:
    """``"2/19 = 10.5% [2.9, 31.4]"``; counts only when ``n < min_n``; ``"n/a"`` for n = 0."""
    if n == 0:
        return "n/a"
    if n < min_n:
        return f"{successes}/{n}"
    low, high = wilson(successes, n) or (0.0, 0.0)
    return f"{successes}/{n} = {successes / n * 100:.1f}% [{low * 100:.1f}, {high * 100:.1f}]"


def _headline_row(name: str, h: dict[str, Any]) -> str:
    return (
        f"| {name} | {rate_text(h['false_alarms'], h['real'])} "
        f"| {rate_text(h['detected'], h['fabricated'])} "
        f"| {h['unchecked_real'] + h['unchecked_fabricated']} |"
    )


def _f1(scores: dict[str, Any]) -> str:
    return "n/a" if scores["f1"] is None else f"{scores['f1'] * 100:.1f}%"


def run_section(title: str, run: dict[str, Any]) -> list[str]:
    """One run (dataset part x input format) as a Markdown section."""
    lines = [
        f"### {title}",
        "",
        f"{run['rows']} references, {run['credits_used']} live searches in this run. "
        "Rates show counts and a 95% Wilson interval.",
        "",
        "| Subset | False alarms on real references | Detection of fabricated references "
        "| Unchecked |",
        "| --- | --- | --- | ---: |",
        _headline_row("All", run["headline"]),
        _headline_row("Indian journals and books", run["indian_subset"]),
        "",
        f"Detection per perturbation type (counts only when fewer than {MIN_RATE_N} rows):",
        "",
        "| Perturbation | Detected |",
        "| --- | --- |",
    ]
    for name, stats in run["per_perturbation"].items():
        detected = rate_text(stats["detected"], stats["rows"], min_n=MIN_RATE_N)
        lines.append(f"| {name.replace('_', ' ')} | {detected} |")
    lines += ["", "| Class | Precision | Recall | F1 |", "| --- | --- | --- | ---: |"]
    for name, s in {"Flagged (any problem)": run["flagged_binary"], **run["classes"]}.items():
        lines.append(
            f"| {name} | {rate_text(s['tp'], s['tp'] + s['fp'])} "
            f"| {rate_text(s['tp'], s['tp'] + s['fn'])} | {_f1(s)} |"
        )
    verdicts = list(next(iter(run["confusion"].values())))
    lines += [
        "",
        "Confusion matrix (rows: expected, columns: GhostCite):",
        "",
        "| Expected | " + " | ".join(verdicts) + " |",
        "| --- | " + " | ".join("---:" for _ in verdicts) + " |",
    ]
    for expected, counts in run["confusion"].items():
        lines.append(f"| {expected} | " + " | ".join(str(counts[v]) for v in verdicts) + " |")
    lines += ["", "Failures:", ""]
    if not run["failures"]:
        lines.append("None.")
    for failure in run["failures"]:
        lines.append(
            f"- `{failure['id']}` ({failure['type']}"
            + (f", {failure['perturbation'].replace('_', ' ')}" if failure["perturbation"] else "")
            + f"): GhostCite said {failure['verdict']}. {failure['reason']}"
        )
    if run["class_differences"]:
        lines += ["", "Detected, but with a different verdict than labelled:", ""]
        lines += [
            f"- `{d['id']}`: expected {d['expected']}, got {d['verdict']}. {d['reason']}"
            for d in run["class_differences"]
        ]
    return [*lines, ""]


def to_markdown(results: dict[str, Any], note: str = POST_FIX_NOTE) -> str:
    """The whole results file: held-out parts first, then the tuning set.

    ``note`` says whether the numbers are a held-out estimate. Every v1 run made after the
    test-informed fixes is not, so that is the default.
    """
    dataset = results["dataset"]
    header = (
        f"Dataset: {dataset['validated']} validated references "
        f"({dataset['dropped']} dropped by validation)."
    )
    if "dataset_sha256" in results:
        header += f" SHA-256 `{results['dataset_sha256']}`."
    else:
        header += f" Split seed {results['seed']}. Thresholds were tuned on the tuning split only."
    lines = ["# GhostCite evaluation results", "", header, "", note, ""]
    for part in _PART_LABELS:
        for input_format in ("text", "bibtex"):
            key = f"{part}/{input_format}"
            if key in results["runs"]:
                label = "raw reference strings" if input_format == "text" else "BibTeX"
                lines += run_section(f"{_PART_LABELS[part]}, {label}", results["runs"][key])
    return "\n".join(lines)
