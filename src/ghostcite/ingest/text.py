"""Plain-text input: pasted reference lists or ``.txt`` files."""

from __future__ import annotations

from ghostcite.errors import InputError
from ghostcite.ingest.sections import find_reference_section
from ghostcite.parse.cleanup import clean_text
from ghostcite.parse.split import SourceLine


def decode_text(data: bytes) -> str:
    """Decode uploaded bytes as text.

    UTF-8 (with or without BOM) is tried first. Windows-1252 is the fallback, because
    many ``.bib`` and ``.txt`` files exported on Windows use it. Bytes containing NUL
    are binary data, not text.
    """
    if b"\x00" in data:
        raise InputError(
            "This file is not text. Upload a PDF, a .bib file or a plain-text reference list."
        )
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise InputError("The file is not valid UTF-8 or Windows-1252 text.") from exc


def text_lines(text: str) -> list[SourceLine]:
    """Return the reference lines of ``text``.

    When the text contains a References/Bibliography heading, only the section after it
    is used. Otherwise the whole text is taken to be the reference list, which is the
    normal case for pasted references. Line numbers refer to the original text.
    """
    lines = [
        SourceLine(line, number) for number, line in enumerate(clean_text(text).split("\n"), 1)
    ]
    section = find_reference_section(lines)
    return section if section is not None else lines
