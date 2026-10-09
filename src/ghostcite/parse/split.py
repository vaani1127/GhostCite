"""Split a reference section into individual references.

Numbered styles (``[1]``, ``1.``, ``(1)``) are detected by markers at line starts. A
marker only opens a new reference when its number is the next one in sequence, so a
wrapped line that happens to begin with "12." or "(2019)" is never mistaken for a new
entry. Unnumbered lists (author-year styles) are split on blank lines when present,
otherwise on lines that start like an author name after a line that ended a sentence.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from ghostcite.parse.cleanup import join_lines


@dataclass(frozen=True, slots=True)
class SourceLine:
    """One line of input text and its 1-based line number, when meaningful."""

    text: str
    number: int | None = None


@dataclass(frozen=True, slots=True)
class RawReference:
    """The text of one reference and the line where it starts."""

    text: str
    line: int | None = None


_MARKERS: dict[str, re.Pattern[str]] = {
    "bracket": re.compile(r"^\s*\[(\d{1,4})\]\s*"),
    "paren": re.compile(r"^\s*\((\d{1,4})\)\s+"),
    "dot": re.compile(r"^\s*(\d{1,4})\.\s+(?=\D)"),
}
_INLINE_BRACKET = re.compile(r"(?<=\S)\s+(?=\[\d{1,4}\]\s)")
# A line that opens an author-year reference: "Surname, I." / "Surname, Given" /
# "Surname AK," (Vancouver) / "A. K. Surname". Deliberately strict, so a wrapped venue line
# such as "Neural Information Processing Systems" never starts a new reference.
_NAME = r"[A-Z\u00c0-\u024f][\w'\u2019-]+"
_AUTHOR_START = re.compile(
    rf"^(?:{_NAME}(?:[ -]{_NAME})?,\s+[A-Z]|{_NAME}\s+[A-Z]{{1,3}}[,.]|(?:[A-Z]\.\s?)+{_NAME})"
)
_SENTENCE_END = re.compile(r"[.)\]]$|\d$")
_MIN_RUN = 2


def _explode_inline_brackets(lines: Sequence[SourceLine]) -> list[SourceLine]:
    """Put each ``[n]`` reference on its own line when several share one line (pasted text)."""
    result: list[SourceLine] = []
    for line in lines:
        pieces = _INLINE_BRACKET.split(line.text)
        result.extend(SourceLine(piece, line.number) for piece in pieces)
    return result


def _marker_numbers(lines: Sequence[SourceLine], marker: re.Pattern[str]) -> list[int | None]:
    """The marker number at the start of each line, or ``None`` where there is none."""
    numbers: list[int | None] = []
    for line in lines:
        match = marker.match(line.text)
        numbers.append(int(match.group(1)) if match else None)
    return numbers


def _sequence_starts(numbers: Sequence[int | None]) -> list[int]:
    """Return the indices of lines that open a reference (markers n, n+1, n+2 and so on).

    The sequence starts at the first marker numbered 0 or 1 (lists almost always start
    there), or at the first marker at all. Out-of-sequence markers ("2019." or "12." on a
    wrapped line) are continuation text and are ignored.
    """
    present = [n for n in numbers if n is not None]
    if not present:
        return []
    expected = next((n for n in present if n <= 1), present[0])
    starts: list[int] = []
    for index, number in enumerate(numbers):
        if number == expected:
            starts.append(index)
            expected += 1
    return starts


def _detect_numbering(lines: Sequence[SourceLine]) -> re.Pattern[str] | None:
    runs = {
        name: len(_sequence_starts(_marker_numbers(lines, marker)))
        for name, marker in _MARKERS.items()
    }
    name, run = max(runs.items(), key=lambda item: item[1])
    return _MARKERS[name] if run >= _MIN_RUN else None


def _split_numbered(lines: Sequence[SourceLine], marker: re.Pattern[str]) -> list[RawReference]:
    starts = set(_sequence_starts(_marker_numbers(lines, marker)))
    groups: list[tuple[int | None, list[str]]] = []
    for index, line in enumerate(lines):
        if index in starts:
            match = marker.match(line.text)
            body = line.text[match.end() :] if match else line.text
            groups.append((line.number, [body]))
        elif groups:
            groups[-1][1].append(line.text)
        # Lines before the first marker are section noise and are dropped.
    return _to_references(groups)


def _split_blocks(lines: Sequence[SourceLine]) -> list[RawReference]:
    groups: list[tuple[int | None, list[str]]] = []
    in_block = False
    for line in lines:
        if not line.text.strip():
            in_block = False
            continue
        if not in_block:
            groups.append((line.number, []))
            in_block = True
        groups[-1][1].append(line.text)
    return _to_references(groups)


def _split_author_year(lines: Sequence[SourceLine]) -> list[RawReference]:
    groups: list[tuple[int | None, list[str]]] = []
    for line in lines:
        text = line.text.strip()
        if not text:
            continue
        previous_ended = bool(groups) and bool(_SENTENCE_END.search(groups[-1][1][-1].strip()))
        if not groups or (previous_ended and _AUTHOR_START.match(text)):
            groups.append((line.number, [text]))
        else:
            groups[-1][1].append(text)
    return _to_references(groups)


def _to_references(groups: list[tuple[int | None, list[str]]]) -> list[RawReference]:
    references = [RawReference(join_lines(parts), number) for number, parts in groups]
    return [ref for ref in references if ref.text]


def split_references(lines: Sequence[SourceLine]) -> list[RawReference]:
    """Split the lines of a reference section into individual references, in order."""
    lines = _explode_inline_brackets(lines)
    marker = _detect_numbering(lines)
    if marker is not None:
        return _split_numbered(lines, marker)
    blocks = _split_blocks(lines)
    by_author = _split_author_year(lines)
    # Blank lines separate references only if they produce about as many groups as the
    # author-start heuristic does. A stray blank line in a one-per-line list must not
    # merge dozens of references into two blocks.
    if len(blocks) > 1 and len(blocks) * 2 >= len(by_author):
        return blocks
    return by_author
