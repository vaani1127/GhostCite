"""The committed sample files agree with each other and run fully from the demo bundle."""

from __future__ import annotations

from pathlib import Path

from ghostcite.document import load_document
from ghostcite.models import RunMode, Verdict
from ghostcite.samples import SAMPLE_BIB, SAMPLE_PDF, SAMPLE_TEXT, sample_path
from ghostcite.service import RunOptions, run_check
from ghostcite.settings import Settings


def _titles(name: str) -> list[str | None]:
    path = sample_path(name)
    document = load_document(path.read_bytes(), path.name)
    return [reference.fields.title for reference in document.references]


def test_pdf_and_text_samples_parse_to_the_same_references() -> None:
    pdf, text = _titles(SAMPLE_PDF), _titles(SAMPLE_TEXT)
    assert len(pdf) == len(text) == 11
    assert pdf == text


def test_every_sample_runs_in_demo_mode_without_skips(tmp_path: Path) -> None:
    settings = Settings(api_key=None, cache_dir=tmp_path)
    for name in (SAMPLE_BIB, SAMPLE_TEXT, SAMPLE_PDF):
        path = sample_path(name)
        document = load_document(path.read_bytes(), path.name)
        report = run_check(document, settings, RunOptions(mode=RunMode.DEMO))
        assert report.summary.credits_used == 0
        assert report.summary.counts.get(Verdict.SKIPPED_BUDGET, 0) == 0
        assert report.summary.integrity_score == 72.7
