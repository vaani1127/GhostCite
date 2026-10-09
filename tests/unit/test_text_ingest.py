from __future__ import annotations

import pytest

from ghostcite.errors import InputError
from ghostcite.ingest.text import decode_text, text_lines


def test_decode_utf8_with_and_without_bom() -> None:
    assert decode_text("caf\u00e9".encode()) == "caf\u00e9"
    assert decode_text(b"\xef\xbb\xbfcaf\xc3\xa9") == "caf\u00e9"


def test_decode_windows_1252_fallback() -> None:
    assert decode_text(b"M\xfcller \x93quoted\x94") == "M\u00fcller \u201cquoted\u201d"


def test_binary_is_rejected() -> None:
    with pytest.raises(InputError, match="not text"):
        decode_text(b"\x00\x01\x02binary")


def test_undecodable_bytes_are_rejected() -> None:
    # 0x81 is undefined in Windows-1252 and invalid as a UTF-8 start byte.
    with pytest.raises(InputError, match="not valid"):
        decode_text(b"abc \x81 def")


def test_whole_text_is_used_without_a_heading() -> None:
    lines = text_lines("[1] First.\r\n[2] Second.")
    assert [(line.text, line.number) for line in lines] == [("[1] First.", 1), ("[2] Second.", 2)]


def test_section_after_heading_keeps_original_line_numbers() -> None:
    lines = text_lines("My essay text.\n\nReferences\n[1] First.\n[2] Second.")
    assert [(line.text, line.number) for line in lines] == [("[1] First.", 4), ("[2] Second.", 5)]
