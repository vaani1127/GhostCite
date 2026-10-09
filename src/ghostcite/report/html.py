"""Self-contained HTML report: one file, inline CSS and JS, no external requests.

The file can be e-mailed or attached to a review and opened offline. Jinja2 autoescaping
is on, and links are only rendered for ``http(s)`` URLs, so text from search results
can never inject markup or scripts.
"""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlparse

from jinja2 import Environment, PackageLoader, select_autoescape

from ghostcite.models import FieldStatus, Report, Verdict
from ghostcite.report.summary import (
    MODE_LABELS,
    SCORE_FORMULA,
    VERDICT_LABELS,
    cited_title,
    score_text,
)

# Sort order for "most serious first": fabricated, then wrong metadata, then unchecked.
_SEVERITY = {
    Verdict.NOT_FOUND: 0,
    Verdict.METADATA_MISMATCH: 1,
    Verdict.UNPARSEABLE: 2,
    Verdict.SKIPPED_BUDGET: 3,
    Verdict.VERIFIED: 4,
}

_ENV = Environment(
    loader=PackageLoader("ghostcite", "report/templates"),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def safe_url(url: str | None) -> str | None:
    """``url`` if it is an absolute http(s) URL, else ``None`` (blocks ``javascript:`` links)."""
    if not url:
        return None
    parsed = urlparse(url)
    return url if parsed.scheme in {"http", "https"} and parsed.netloc else None


def render_html(
    report: Report,
    *,
    downloads: Sequence[tuple[str, str]] = (),
    home_url: str | None = None,
) -> str:
    """Render the report as a standalone HTML page.

    ``downloads`` (label, URL) and ``home_url`` are only used by the web UI. The file
    exported by the CLI has neither and works offline.
    """
    template = _ENV.get_template("report.html.j2")
    return template.render(
        downloads=downloads,
        home_url=home_url,
        severity=_SEVERITY,
        report=report,
        labels=VERDICT_LABELS,
        mode_label=MODE_LABELS[report.mode],
        verdicts=list(Verdict),
        score=score_text(report),
        formula=SCORE_FORMULA,
        cited_title=cited_title,
        safe_url=safe_url,
        FieldStatus=FieldStatus,
    )
