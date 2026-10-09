from __future__ import annotations

import pytest

from ghostcite.ingest.sections import find_reference_section
from ghostcite.parse.split import SourceLine


def _lines(*texts: str) -> list[SourceLine]:
    return [SourceLine(text, i) for i, text in enumerate(texts, 1)]


@pytest.mark.parametrize(
    "heading",
    ["References", "REFERENCES", "7 References", "VII. REFERENCES", "Bibliography",
     "Works Cited", "Literature Cited", "References:"],
)  # fmt: skip
def test_headings(heading: str) -> None:
    section = find_reference_section(_lines("Intro text", heading, "[1] A ref."))
    assert section is not None
    assert [line.text for line in section] == ["[1] A ref."]


def test_last_heading_wins_over_table_of_contents() -> None:
    lines = _lines("Contents", "References", "Body text", "References", "[1] Real ref.")
    section = find_reference_section(lines)
    assert section is not None
    assert [line.number for line in section] == [5]


def test_section_stops_at_appendix() -> None:
    lines = _lines("References", "[1] Ref one.", "[2] Ref two.", "Appendix A Proofs", "More")
    section = find_reference_section(lines)
    assert section is not None
    assert [line.text for line in section] == ["[1] Ref one.", "[2] Ref two."]


def test_heading_inside_a_sentence_is_ignored() -> None:
    assert find_reference_section(_lines("See the references below for details.")) is None


def test_no_heading() -> None:
    assert find_reference_section(_lines("[1] A ref.")) is None
