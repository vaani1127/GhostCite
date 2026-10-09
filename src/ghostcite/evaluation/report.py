"""Markdown rendering of evaluation results (``eval/results.md``)."""

from __future__ import annotations

from typing import Any


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _headline_rows(name: str, h: dict[str, Any]) -> list[str]:
    return [
        f"| {name} | {h['real']} | {h['false_alarms']} | {_pct(h['false_alarm_rate'])} "
        f"| {h['fabricated']} | {h['detected']} | {_pct(h['detection_rate'])} "
        f"| {h['unchecked_real'] + h['unchecked_fabricated']} |"
    ]


def run_section(title: str, run: dict[str, Any]) -> list[str]:
    """One run (split x input format) as a Markdown section."""
    lines = [
        f"### {title}",
        "",
        f"{run['rows']} references, {run['credits_used']} live searches in this run.",
        "",
    ]
    lines += [
        "| Subset | Real | False alarms | False alarm rate | Fabricated | Detected "
        "| Detection rate | Unchecked |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        *_headline_rows("All", run["headline"]),
        *_headline_rows("Indian journals and books", run["indian_subset"]),
        "",
        "| Perturbation | Rows | Detected | Detection rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, stats in run["per_perturbation"].items():
        lines.append(
            f"| {name.replace('_', ' ')} | {stats['rows']} | {stats['detected']} "
            f"| {_pct(stats['detection_rate'])} |"
        )
    lines += ["", "| Class | Precision | Recall | F1 |", "| --- | ---: | ---: | ---: |"]
    for name, scores in {"Flagged (any problem)": run["flagged_binary"], **run["classes"]}.items():
        lines.append(
            f"| {name} | {_pct(scores['precision'])} | {_pct(scores['recall'])} "
            f"| {_pct(scores['f1'])} |"
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


HELD_OUT_NOTE = (
    "**This is the held-out estimate**: the first and only run on the test split made "
    "before any change informed by it. Quote these test-split numbers."
)
POST_FIX_NOTE = (
    "**Post-fix rerun, not a held-out estimate.** Bugs found while reading the first "
    "test-split run were fixed before this run, so its test-split numbers are optimistic. "
    "Quote `eval/results_heldout_first_run.md` instead; docs/EVALUATION.md explains both."
)


def to_markdown(results: dict[str, Any], note: str = POST_FIX_NOTE) -> str:
    """The whole results file: the test set first, then the tuning set.

    ``note`` says whether the test-split numbers are a held-out estimate. Every run made
    after the test-informed fixes is not, so that is the default.
    """
    lines = [
        "# GhostCite evaluation results",
        "",
        f"Dataset: {results['dataset']['validated']} validated references "
        f"({results['dataset']['dropped']} dropped by validation). Split seed {results['seed']}. "
        "Thresholds were tuned on the tuning split only.",
        "",
        note,
        "",
    ]
    for split in ("test", "tuning"):
        for input_format in ("text", "bibtex"):
            key = f"{split}/{input_format}"
            if key in results["runs"]:
                label = "raw reference strings" if input_format == "text" else "BibTeX"
                lines += run_section(f"{split.title()} split, {label}", results["runs"][key])
    return "\n".join(lines)
