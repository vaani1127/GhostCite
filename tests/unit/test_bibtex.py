from __future__ import annotations

import pytest

from ghostcite.ingest.bibtex import BibtexResult, parse_bibtex
from ghostcite.models import Reference, SourceFormat
from tests.conftest import FIXTURES


@pytest.fixture(scope="module")
def mixed() -> BibtexResult:
    return parse_bibtex((FIXTURES / "bib" / "mixed.bib").read_text(encoding="utf-8"))


def _by_key(result: BibtexResult, key: str) -> list[Reference]:
    return [ref for ref in result.references if ref.key == key]


def test_every_entry_becomes_a_reference_in_order(mixed: BibtexResult) -> None:
    keys = [ref.key for ref in mixed.references]
    assert keys == [
        "vaswani2017attention",
        "mueller2020",
        "broken2019",
        "kalam1999wings",
        "vaswani2017attention",
        "dupfield2022",
        "noauthor2015",
    ]
    assert [ref.index for ref in mixed.references] == list(range(1, 8))
    assert all(ref.source_format is SourceFormat.BIBTEX for ref in mixed.references)


def test_valid_entry_fields(mixed: BibtexResult) -> None:
    ref = _by_key(mixed, "vaswani2017attention")[0]
    fields = ref.fields
    assert fields.title == "Attention Is All You Need"
    assert [a.surname for a in fields.authors] == ["Vaswani", "Shazeer", "Parmar"]
    assert fields.authors[0].given == "Ashish"
    assert fields.et_al
    assert fields.year == 2017
    assert fields.venue == "Advances in Neural Information Processing Systems"
    assert fields.doi == "10.48550/arxiv.1706.03762"
    assert fields.entry_type == "inproceedings"
    assert fields.confidence.title == 1.0
    assert ref.line == 5


def test_latex_accents_particles_and_biblatex_date(mixed: BibtexResult) -> None:
    fields = _by_key(mixed, "mueller2020")[0].fields
    assert fields.title == "\u00dcber die Bedeutung von Daten"
    assert [a.surname for a in fields.authors] == ["M\u00fcller", "de la Fontaine"]
    assert fields.venue == "Zeitschrift f\u00fcr Informatik"
    assert fields.year == 2020


def test_syntax_error_becomes_unparseable_reference_with_line(mixed: BibtexResult) -> None:
    broken = _by_key(mixed, "broken2019")[0]
    assert broken.fields.title is None
    assert broken.line == 20
    assert "This entry never closes" in broken.raw
    assert any(w.startswith("Line 20:") and "syntax error" in w for w in mixed.warnings)


def test_entries_after_a_syntax_error_still_parse(mixed: BibtexResult) -> None:
    kalam = _by_key(mixed, "kalam1999wings")[0].fields
    assert kalam.title == "Wings of Fire: An Autobiography"
    assert [a.surname for a in kalam.authors] == ["Kalam", "Tiwari"]
    assert kalam.venue == "Universities Press"
    assert kalam.entry_type == "book"


def test_duplicate_key_keeps_both_entries_and_warns(mixed: BibtexResult) -> None:
    duplicates = _by_key(mixed, "vaswani2017attention")
    assert [d.fields.title for d in duplicates] == ["Attention Is All You Need", "A duplicate key"]
    assert any("duplicate citation key 'vaswani2017attention'" in w for w in mixed.warnings)


def test_duplicate_field_is_recovered_and_warned(mixed: BibtexResult) -> None:
    ref = _by_key(mixed, "dupfield2022")[0]
    assert ref.fields.title in {"First title", "Second title"}
    assert any("'dupfield2022' repeats a field" in w for w in mixed.warnings)


def test_missing_author_field(mixed: BibtexResult) -> None:
    fields = _by_key(mixed, "noauthor2015")[0].fields
    assert fields.authors == ()
    assert fields.confidence.authors == 0.0
    assert fields.venue == "Thapar Institute of Engineering and Technology"
    assert fields.entry_type == "phdthesis"


def test_editor_used_when_no_author() -> None:
    result = parse_bibtex("@book{b, title={Edited Volume Title}, editor={Rao, P.}, year={2001}}")
    assert [a.surname for a in result.references[0].fields.authors] == ["Rao"]


def test_empty_and_comment_only_input() -> None:
    assert parse_bibtex("").references == []
    assert parse_bibtex("% only a comment\n@comment{nothing}").references == []


def test_entry_without_year_or_title() -> None:
    fields = parse_bibtex("@misc{m, note={nothing useful}}").references[0].fields
    assert fields.title is None
    assert fields.year is None
    assert fields.confidence.title == 0.0
