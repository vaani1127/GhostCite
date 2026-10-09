"""Markdown report, readable on GitHub and in pull-request comments."""

from __future__ import annotations

from ghostcite.models import ReferenceResult, Report, Verdict
from ghostcite.report.summary import (
    SCORE_FORMULA,
    VERDICT_LABELS,
    cited_title,
    score_text,
)


def _cell(text: str) -> str:
    """Make ``text`` safe inside a Markdown table cell."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def _evidence(result: ReferenceResult) -> str:
    match = result.best_match
    if match is None:
        return ""
    candidate = match.candidate
    title = _cell(candidate.title)
    return f"[{title}]({candidate.link})" if candidate.link else title


def render_markdown(report: Report) -> str:
    """Summary, verdict counts, then one table row per reference."""
    summary = report.summary
    lines = [
        f"# GhostCite report: {_cell(report.source_name)}",
        "",
        f"Generated {report.generated_at:%Y-%m-%d %H:%M} UTC by GhostCite {report.tool_version} "
        f"({report.mode.value} mode).",
        "",
        f"**Integrity score: {score_text(report)}**. {summary.checked} of {summary.total} "
        f"references checked, {summary.credits_used} SerpApi searches used, "
        f"{summary.cache_hits} answered from cache.",
        "",
        f"_{SCORE_FORMULA}_",
        "",
        "| Verdict | References |",
        "| --- | ---: |",
        *(f"| {VERDICT_LABELS[v]} | {summary.counts.get(v, 0)} |" for v in Verdict),
        "",
    ]
    if report.warnings:
        lines += ["## Warnings", "", *(f"- {_cell(w)}" for w in report.warnings), ""]
    lines += [
        "## References",
        "",
        "| # | Verdict | Confidence | Cited title | Reason | Best match |",
        "| ---: | --- | ---: | --- | --- | --- |",
    ]
    for result in report.results:
        lines.append(
            f"| {result.reference.index} | {VERDICT_LABELS[result.verdict]} "
            f"| {result.confidence:.2f} | {_cell(cited_title(result))} "
            f"| {_cell(result.reason)} | {_evidence(result)} |"
        )
    return "\n".join(lines) + "\n"
