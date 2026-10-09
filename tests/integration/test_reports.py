from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft4Validator

from ghostcite.document import load_document, load_text
from ghostcite.models import Report, RunMode, Verdict
from ghostcite.pipeline import check_document
from ghostcite.report import OutputFormat, render
from ghostcite.report.html import safe_url
from ghostcite.report.sarif import FINGERPRINT_KEY
from ghostcite.search.budget import SearchBudget
from ghostcite.search.cache import SqliteCache
from ghostcite.search.client import SearchClient
from tests.conftest import FIXTURES
from tests.helpers import ATTENTION, BOOK, FABRICATED, WRONG_YEAR, FixtureTransport, numbered

SECOND_REFERENCE = '[2] B. Jones, "Another fake title here," 2021.'
SCHEMA = json.loads((FIXTURES / "schemas" / "sarif-2.1.0.json").read_text(encoding="utf-8"))


def _report(tmp_path: Path, text: str | None = None, bib: bool = False) -> Report:
    if bib:
        document = load_document((FIXTURES / "bib" / "mixed.bib").read_bytes(), "refs/mixed.bib")
    else:
        document = load_text(text or numbered(ATTENTION, WRONG_YEAR, FABRICATED, BOOK))
    with SqliteCache(tmp_path / "cache", 3600) as cache:
        client = SearchClient(cache, FixtureTransport(), SearchBudget(50))
        return check_document(document, client, mode=RunMode.LIVE)


@pytest.fixture
def report(tmp_path: Path) -> Report:
    return _report(tmp_path)


def test_json_round_trips(report: Report) -> None:
    text = render(report, OutputFormat.JSON)
    assert Report.model_validate_json(text) == report
    assert json.loads(text)["summary"]["counts"]["VERIFIED"] == 2


def test_markdown_lists_every_reference(report: Report) -> None:
    text = render(report, OutputFormat.MARKDOWN)
    assert text.startswith("# GhostCite report: pasted-text")
    assert "**Integrity score: 62.5 / 100**" in text
    assert (
        "| 2 | Metadata mismatch | 1.00 | Attention is all you need "
        "| Title matches, but year is 2017, not 2019. (Google Scholar lists this work "
        "with 26 versions; this may be a different version.) |" in text
    )
    assert "[Attention is all you need](https://" in text
    assert text.count("\n| ") >= 4 + 5


def test_markdown_escapes_table_breaking_characters(tmp_path: Path) -> None:
    text = render(
        _report(
            tmp_path,
            '[1] A. Smith, "Pipes | and \\ backslashes in a title," 2020.\n' + SECOND_REFERENCE,
        ),
        OutputFormat.MARKDOWN,
    )
    assert "Pipes \\| and \\\\ backslashes in a title" in text


def test_markdown_shows_warnings(tmp_path: Path) -> None:
    text = render(_report(tmp_path, bib=True), OutputFormat.MARKDOWN)
    assert "## Warnings" in text
    assert "duplicate citation key" in text


def test_html_is_self_contained_and_escaped(tmp_path: Path) -> None:
    hostile = '[1] A. Smith, "<script>alert(1)</script> injected title text," 2020.\n'
    hostile += SECOND_REFERENCE
    html = render(_report(tmp_path, hostile), OutputFormat.HTML)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert 'src="http' not in html  # no external resources
    assert "<link" not in html
    assert "Content-Security-Policy" in html


def test_html_contains_scores_filters_and_evidence(report: Report) -> None:
    html = render(report, OutputFormat.HTML)
    assert "62.5 / 100" in html
    assert 'data-filter="NOT_FOUND"' in html
    assert 'rel="noopener noreferrer"' in html
    assert "Found only via Google web search" in html
    assert html.count('<tr data-verdict="') == 4


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://doi.org/10.1/x", "https://doi.org/10.1/x"),
        ("http://example.org/a", "http://example.org/a"),
        ("javascript:alert(1)", None),
        ("/relative/path", None),
        ("", None),
        (None, None),
    ],
)
def test_safe_url(url: str | None, expected: str | None) -> None:
    assert safe_url(url) == expected


def test_sarif_validates_against_the_official_schema(tmp_path: Path) -> None:
    for report in (_report(tmp_path / "a"), _report(tmp_path / "b", bib=True)):
        log = json.loads(render(report, OutputFormat.SARIF, artifact_uri="refs\\mixed.bib"))
        errors = sorted(Draft4Validator(SCHEMA).iter_errors(log), key=str)
        assert not errors, errors[0].message


def test_sarif_points_at_bibtex_lines(tmp_path: Path) -> None:
    report = _report(tmp_path, bib=True)
    log = json.loads(render(report, OutputFormat.SARIF, artifact_uri="refs\\mixed.bib"))
    results = log["runs"][0]["results"]
    by_key = {r["message"]["text"].split("]")[0].lstrip("["): r for r in results}
    broken = by_key["broken2019"]
    assert broken["ruleId"] == "GC003"
    assert broken["level"] == "warning"
    location = broken["locations"][0]["physicalLocation"]
    assert location == {"artifactLocation": {"uri": "refs/mixed.bib"}, "region": {"startLine": 20}}
    assert all(r["properties"]["verdict"] != "VERIFIED" for r in results)
    assert len({r["partialFingerprints"][FINGERPRINT_KEY] for r in results}) == len(results)


def test_sarif_levels_and_rules(report: Report) -> None:
    log = json.loads(render(report, OutputFormat.SARIF))
    run = log["runs"][0]
    levels = {r["properties"]["verdict"]: r["level"] for r in run["results"]}
    assert levels == {"METADATA_MISMATCH": "warning", "NOT_FOUND": "error"}
    assert [rule["id"] for rule in run["tool"]["driver"]["rules"]] == [
        "GC001",
        "GC002",
        "GC003",
        "GC004",
    ]
    assert run["properties"]["integrityScore"] == 62.5
    # Pasted text keeps line numbers: reference 2 starts on line 2.
    location = run["results"][0]["locations"][0]["physicalLocation"]
    assert location == {"artifactLocation": {"uri": "pasted-text"}, "region": {"startLine": 2}}


def test_sarif_omits_the_region_without_a_line_number(report: Report) -> None:
    # PDF references have no meaningful line numbers.
    unlined = tuple(
        r.model_copy(update={"reference": r.reference.model_copy(update={"line": None})})
        for r in report.results
    )
    log = json.loads(render(report.model_copy(update={"results": unlined}), OutputFormat.SARIF))
    for result in log["runs"][0]["results"]:
        assert "region" not in result["locations"][0]["physicalLocation"]


def test_sarif_is_stable_across_runs(tmp_path: Path) -> None:
    first = json.loads(render(_report(tmp_path / "1"), OutputFormat.SARIF))
    second = json.loads(render(_report(tmp_path / "2"), OutputFormat.SARIF))
    assert first["runs"][0]["results"] == second["runs"][0]["results"]


def test_output_format_metadata() -> None:
    assert OutputFormat.SARIF.media_type == "application/sarif+json"
    assert OutputFormat.MARKDOWN.extension == ".md"
    assert {f.extension for f in OutputFormat} == {".json", ".md", ".html", ".sarif"}
    assert Verdict.NOT_FOUND.value == "NOT_FOUND"
