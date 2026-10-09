"""Render a :class:`ghostcite.models.Report` as JSON, Markdown, HTML or SARIF."""

from __future__ import annotations

from enum import StrEnum

from ghostcite.models import Report
from ghostcite.report.html import render_html
from ghostcite.report.json_report import render_json
from ghostcite.report.markdown import render_markdown
from ghostcite.report.sarif import render_sarif


class OutputFormat(StrEnum):
    """File formats GhostCite can write."""

    JSON = "json"
    MARKDOWN = "md"
    HTML = "html"
    SARIF = "sarif"

    @property
    def media_type(self) -> str:
        """HTTP content type for downloads from the web UI."""
        return {
            OutputFormat.JSON: "application/json",
            OutputFormat.MARKDOWN: "text/markdown; charset=utf-8",
            OutputFormat.HTML: "text/html; charset=utf-8",
            OutputFormat.SARIF: "application/sarif+json",
        }[self]

    @property
    def extension(self) -> str:
        """File extension for downloads."""
        return {
            OutputFormat.JSON: ".json",
            OutputFormat.MARKDOWN: ".md",
            OutputFormat.HTML: ".html",
            OutputFormat.SARIF: ".sarif",
        }[self]


def render(report: Report, output_format: OutputFormat, *, artifact_uri: str | None = None) -> str:
    """Render ``report`` in ``output_format``.

    ``artifact_uri`` is the path SARIF results point at (for code scanning, relative to
    the repository root). It defaults to the report's source name.
    """
    if output_format is OutputFormat.JSON:
        return render_json(report)
    if output_format is OutputFormat.MARKDOWN:
        return render_markdown(report)
    if output_format is OutputFormat.HTML:
        return render_html(report)
    return render_sarif(report, artifact_uri or report.source_name)
