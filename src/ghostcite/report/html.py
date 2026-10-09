"""Self-contained HTML report: one file, inline CSS and JS, no external requests.

The file can be e-mailed or attached to a review and opened offline. Jinja2 autoescaping
is on, and links are only rendered for ``http(s)`` URLs, so text from search results
can never inject markup or scripts.
"""

from __future__ import annotations

from urllib.parse import urlparse

from jinja2 import Environment, PackageLoader, select_autoescape

from ghostcite.models import FieldStatus, Report, Verdict
from ghostcite.report.summary import SCORE_FORMULA, VERDICT_LABELS, cited_title, score_text

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


def render_html(report: Report) -> str:
    """Render the report as a standalone HTML page."""
    template = _ENV.get_template("report.html.j2")
    return template.render(
        report=report,
        labels=VERDICT_LABELS,
        verdicts=list(Verdict),
        score=score_text(report),
        formula=SCORE_FORMULA,
        cited_title=cited_title,
        safe_url=safe_url,
        FieldStatus=FieldStatus,
    )
