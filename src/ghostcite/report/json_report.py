"""Machine-readable JSON: the full report model, stable field names, ISO dates."""

from __future__ import annotations

from ghostcite.models import Report


def render_json(report: Report) -> str:
    """Serialize the complete report; it can be loaded back with ``Report.model_validate_json``."""
    return report.model_dump_json(indent=2) + "\n"
