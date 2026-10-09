"""Locate the reference list inside a full document."""

from __future__ import annotations

import re
from collections.abc import Sequence

from ghostcite.parse.split import SourceLine

# A heading line, optionally numbered ("7 References", "VII. REFERENCES").
_HEADING = re.compile(
    r"^\s*(?:(?:\d{1,2}|[IVXLC]{1,6})\.?\s+)?"
    r"(?:references|bibliography|works\s+cited|literature\s+cited|reference\s+list"
    r"|cited\s+literature|references\s+and\s+notes|literature)\s*:?\s*$",
    re.IGNORECASE,
)
# Sections that commonly follow the references and must not be parsed as references.
_END = re.compile(
    r"^\s*(?:(?:[A-Z]|\d{1,2}|[IVXLC]{1,6})[.:]?\s+)?"
    r"(?:appendix|appendices|supplementary\s+(?:materials?|information)|supporting\s+information"
    r"|author\s+biograph(?:y|ies)|about\s+the\s+authors?)\b",
    re.IGNORECASE,
)


def find_reference_section(lines: Sequence[SourceLine]) -> list[SourceLine] | None:
    """Return the lines between the last references heading and the next end section.

    The *last* heading is used because "References" can also appear earlier, in a table
    of contents. Returns ``None`` when no heading exists.
    """
    starts = [i for i, line in enumerate(lines) if _HEADING.match(line.text)]
    if not starts:
        return None
    section: list[SourceLine] = []
    for line in lines[starts[-1] + 1 :]:
        if section and _END.match(line.text):
            break
        section.append(line)
    return section
