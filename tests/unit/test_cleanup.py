from __future__ import annotations

import pytest

from ghostcite.parse.cleanup import clean_text, join_lines


def test_clean_text_folds_ligatures_and_keeps_accents() -> None:
    assert clean_text("e\ufb03cient caf\u00e9") == "efficient caf\u00e9"


def test_clean_text_removes_invisible_characters_and_odd_spaces() -> None:
    raw = "Deep\u00adlearn\u200bing\u00a0for\u2003all  "
    assert clean_text(raw) == "Deeplearning for all"


def test_clean_text_normalizes_newlines_per_line() -> None:
    assert clean_text("  a  b \r\n c\rd ") == "a b\nc\nd"


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["Attention is all you", "need."], "Attention is all you need."),
        (["hyphen-", "ation works"], "hyphenation works"),
        (["state-of-the-", "art models"], "state-of-the-art models"),
        (["Jean-", "Pierre Dupont"], "Jean-Pierre Dupont"),
        (["pp. 1-", "10"], "pp. 1-10"),
        (["doi 10.1000/abc-", "Def"], "doi 10.1000/abc-Def"),
        (["Title -", "Subtitle"], "Title - Subtitle"),
        (["", "  only  ", ""], "only"),
        ([], ""),
    ],
)
def test_join_lines(lines: list[str], expected: str) -> None:
    assert join_lines(lines) == expected
