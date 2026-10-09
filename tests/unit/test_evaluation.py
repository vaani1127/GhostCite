"""The evaluation library: dataset rules, registry validation, styles, split and metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ghostcite.document import load_document, load_text
from ghostcite.evaluation.dataset import EvalRow, Kind, Perturbation, load_dataset
from ghostcite.evaluation.metrics import Outcome, summarize
from ghostcite.evaluation.report import HELD_OUT_NOTE, POST_FIX_NOTE, to_markdown
from ghostcite.evaluation.split import Split, split_rows
from ghostcite.evaluation.styles import Style, assign_styles, render, to_bibtex
from ghostcite.evaluation.validate import (
    ARXIV_QUERY,
    CROSSREF_WORK,
    to_json,
    validate_rows,
)
from ghostcite.match.score import is_title_match
from ghostcite.models import Verdict
from tests.conftest import FIXTURES

REGISTRY = FIXTURES / "registry"
DATASET = Path(__file__).resolve().parents[2] / "eval" / "dataset.jsonl"


def _row(**overrides: Any) -> EvalRow:
    data: dict[str, Any] = {
        "id": "cs-lecun-2015",
        "kind": "real",
        "field": "cs",
        "indian": False,
        "entry_type": "article",
        "title": "Deep learning",
        "authors": [["LeCun", "Yann"], ["Bengio", "Yoshua"], ["Hinton", "Geoffrey"]],
        "year": 2015,
        "venue": "Nature",
        "volume": "521",
        "pages": "436-444",
        "doi": "10.1038/nature14539",
        "expected": "VERIFIED",
    }
    data.update(overrides)
    return EvalRow.model_validate(data)


# ---------------------------------------------------------------- dataset


def test_the_committed_dataset_loads() -> None:
    rows = load_dataset(DATASET)
    assert len(rows) >= 60
    assert {p for r in rows if (p := r.perturbation)} == set(Perturbation)
    assert any(r.indian for r in rows)
    assert all(r.doi or r.arxiv_id for r in rows if r.kind is Kind.REAL)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"doi": None}, "needs a DOI"),
        ({"expected": "NOT_FOUND"}, "expected VERIFIED"),
        ({"kind": "fabricated", "doi": None}, "needs a perturbation"),
        (
            {"kind": "fabricated", "perturbation": "wrong_year",
             "expected": "METADATA_MISMATCH"},
            "only invented",
        ),
        (
            {"kind": "fabricated", "perturbation": "invented",
             "expected": "METADATA_MISMATCH"},
            "expect NOT_FOUND",
        ),
    ],
)  # fmt: skip
def test_row_consistency_rules(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _row(**overrides)


def test_dataset_file_rules(tmp_path: Path) -> None:
    row = _row().model_dump(mode="json")
    duplicate = tmp_path / "dup.jsonl"
    duplicate.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_dataset(duplicate)
    orphan = tmp_path / "orphan.jsonl"
    fake = {**row, "id": "fab-x", "kind": "fabricated", "perturbation": "wrong_year",
            "expected": "METADATA_MISMATCH", "source": "missing", "doi": None}  # fmt: skip
    orphan.write_text(json.dumps(fake) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown sources"):
        load_dataset(orphan)


# ---------------------------------------------------------------- validation


def _fetch(responses: dict[str, str]) -> Any:
    def fetch(url: str) -> str:
        for fragment, body in responses.items():
            if fragment in url:
                return body
        raise OSError(f"no recorded response for {url}")

    return fetch


def _registry(name: str) -> str:
    return (REGISTRY / name).read_text(encoding="utf-8")


def test_real_rows_are_checked_against_crossref_and_arxiv() -> None:
    vaswani = _row(id="cs-vaswani-2017", title="Attention is all you need", doi=None,
                   arxiv_id="1706.03762", authors=[["Vaswani", "Ashish"]], year=2017)  # fmt: skip
    fetch = _fetch({"10.1038/nature14539": _registry("crossref_work_lecun.json"),
                    "1706.03762": _registry("arxiv_vaswani.xml")})  # fmt: skip
    results = validate_rows([_row(), vaswani], fetch)
    assert results["cs-lecun-2015"].ok
    assert results["cs-lecun-2015"].record is not None
    assert results["cs-lecun-2015"].record.source == "crossref"
    assert results["cs-vaswani-2017"].ok
    assert CROSSREF_WORK.startswith("https://")
    assert ARXIV_QUERY.startswith("https://")


def test_disagreements_are_reported() -> None:
    wrong = _row(title="Deep learning for everything", authors=[["Smith", "J"]], year=2001)
    fetch = _fetch({"nature14539": _registry("crossref_work_lecun.json")})
    result = validate_rows([wrong], fetch)[wrong.id]
    assert not result.ok
    assert len(result.problems) == 3


def test_book_with_subtitle_variant_validates() -> None:
    book = _row(id="in-sen-2009", title="The idea of justice", doi="10.2307/j.ctvjnrv7n",
                authors=[["Sen", "Amartya"]], year=2009, entry_type="book")  # fmt: skip
    result = validate_rows([book], _fetch({"ctvjnrv7n": _registry("crossref_work_sen_book.json")}))
    assert result[book.id].ok


def test_lookup_failures_drop_the_row_and_its_perturbations() -> None:
    derived = _row(
        id="fab-year-lecun",
        kind="fabricated",
        perturbation="wrong_year",
        expected="METADATA_MISMATCH",
        source="cs-lecun-2015",
        doi=None,
        year=2011,
    )
    results = validate_rows([_row(), derived], _fetch({}))
    assert not results["cs-lecun-2015"].ok
    assert "lookup failed" in results["cs-lecun-2015"].problems[0]
    assert not results["fab-year-lecun"].ok
    assert results["fab-year-lecun"].problems == ("source row cs-lecun-2015 did not validate",)


def test_invented_rows_must_have_no_close_crossref_match() -> None:
    invented = _row(
        id="fab-invented-sepsis",
        kind="fabricated",
        perturbation="invented",
        expected="NOT_FOUND",
        doi=None,
        title="Adaptive Ayurvedic biomarker panels for early sepsis triage in rural Rajasthan",
    )
    found = validate_rows(
        [invented], _fetch({"query.bibliographic": _registry("crossref_search_invented.json")})
    )
    assert found[invented.id].ok
    real_title = invented.model_copy(update={"title": "Deep learning"})
    hit = json.dumps({"message": {"items": [{"title": ["Deep learning"]}]}})
    assert not validate_rows([real_title], _fetch({"query.bibliographic": hit}))[invented.id].ok
    assert not validate_rows([invented], _fetch({}))[invented.id].ok


def test_validation_report_is_serializable() -> None:
    results = validate_rows(
        [_row()], _fetch({"nature14539": _registry("crossref_work_lecun.json")})
    )
    payload = to_json(results)
    assert payload["cs-lecun-2015"]["ok"] is True
    assert payload["cs-lecun-2015"]["record"]["first_author"] == "LeCun"
    json.dumps(payload)


# ---------------------------------------------------------------- styles


BOOK = _row(id="in-sen-2009", title="The idea of justice", authors=[["Sen", "Amartya"]],
            year=2009, venue="Harvard University Press", entry_type="book",
            doi="10.2307/j.ctvjnrv7n", volume=None, pages=None)  # fmt: skip


@pytest.mark.parametrize("style", list(Style))
@pytest.mark.parametrize("row", [_row(), BOOK], ids=["article", "book"])
def test_every_style_parses_back(style: Style, row: EvalRow) -> None:
    reference = load_text("[1] " + render(row, style)).references[0]
    fields = reference.fields
    assert fields.title is not None
    assert is_title_match(fields.title, row.title)
    assert fields.authors[0].surname == row.authors[0][0]
    assert fields.year == row.year


def test_bibtex_rendering_parses_back() -> None:
    document = load_document(to_bibtex([_row(), BOOK]).encode(), "eval.bib")
    assert [r.key for r in document.references] == ["cs-lecun-2015", "in-sen-2009"]
    assert document.references[1].fields.entry_type == "book"
    assert document.references[1].fields.venue == "Harvard University Press"


def test_style_assignment_is_balanced_and_fixed() -> None:
    rows = [_row(id=f"cs-row-{i}") for i in range(8)]
    first, second = assign_styles(rows, 7), assign_styles(rows, 7)
    assert first == second
    assert sorted(first.values()).count(Style.APA) == 2


# ---------------------------------------------------------------- split


def test_split_is_deterministic_and_keeps_families_together() -> None:
    rows = load_dataset(DATASET)
    first, second = split_rows(rows), split_rows(rows)
    assert first == second
    for row in rows:
        if row.source is not None:
            assert first[row.id] is first[row.source]
    tuning = sum(split is Split.TUNING for split in first.values())
    assert 0.3 <= tuning / len(rows) <= 0.5
    assert split_rows(rows, seed=1) != first


# ---------------------------------------------------------------- metrics


def _outcome(row: EvalRow, verdict: Verdict) -> Outcome:
    return Outcome(row, verdict, 0.9, f"reason for {row.id}", row.title, "best")


def test_metrics_and_report() -> None:
    real_ok = _row()
    real_flagged = _row(id="eco-real-flagged", indian=True)
    real_skipped = _row(id="med-real-skipped")
    invented = _row(id="fab-invented-x", kind="fabricated", perturbation="invented",
                    expected="NOT_FOUND", doi=None)  # fmt: skip
    year = _row(id="fab-year-x", kind="fabricated", perturbation="wrong_year",
                expected="METADATA_MISMATCH", doi=None, source="cs-lecun-2015")  # fmt: skip
    venue = _row(id="fab-venue-x", kind="fabricated", perturbation="fake_venue",
                 expected="METADATA_MISMATCH", doi=None, source="cs-lecun-2015")  # fmt: skip
    outcomes = [
        _outcome(real_ok, Verdict.VERIFIED),
        _outcome(real_flagged, Verdict.METADATA_MISMATCH),
        _outcome(real_skipped, Verdict.SKIPPED_BUDGET),
        _outcome(invented, Verdict.NOT_FOUND),
        _outcome(year, Verdict.NOT_FOUND),
        _outcome(venue, Verdict.VERIFIED),
    ]
    summary = summarize(outcomes)
    head = summary["headline"]
    assert (head["real"], head["false_alarms"], head["false_alarm_rate"]) == (3, 1, 0.3333)
    assert (head["fabricated"], head["detected"], head["detection_rate"]) == (3, 2, 0.6667)
    assert head["unchecked_real"] == 1
    assert summary["per_perturbation"]["fake_venue"]["detection_rate"] == 0.0
    assert summary["per_perturbation"]["reworded_title"]["detection_rate"] is None
    assert summary["classes"]["NOT_FOUND"] == {
        "tp": 1,
        "fp": 1,
        "fn": 0,
        "precision": 0.5,
        "recall": 1.0,
        "f1": 0.6667,
    }
    assert summary["indian_subset"]["false_alarm_rate"] == 1.0
    assert summary["confusion"]["VERIFIED"]["SKIPPED_BUDGET"] == 1
    kinds = sorted(f["type"] for f in summary["failures"])
    assert kinds == ["false alarm", "missed fabrication", "real reference not checked"]
    assert summary["class_differences"][0]["id"] == "fab-year-x"

    summary["credits_used"] = 0
    markdown = to_markdown(
        {"dataset": {"validated": 6, "dropped": 0}, "seed": 1, "runs": {"test/text": summary}}
    )
    assert "Test split, raw reference strings" in markdown
    assert "| Indian journals and books | 1 | 1 | 100.0% |" in markdown
    assert "`eco-real-flagged` (false alarm)" in markdown
    assert "Detected, but with a different verdict" in markdown


def test_report_without_failures() -> None:
    summary = summarize([_outcome(_row(), Verdict.VERIFIED)])
    summary["credits_used"] = 0
    markdown = to_markdown(
        {"dataset": {"validated": 1, "dropped": 0}, "seed": 1, "runs": {"tuning/bibtex": summary}}
    )
    assert "Tuning split, BibTeX" in markdown
    assert "None." in markdown
    assert POST_FIX_NOTE in markdown
    assert HELD_OUT_NOTE in to_markdown(
        {"dataset": {"validated": 1, "dropped": 0}, "seed": 1, "runs": {}}, HELD_OUT_NOTE
    )
