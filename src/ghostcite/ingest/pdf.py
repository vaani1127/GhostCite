"""PDF input: extract the reference section with pypdf.

Plain pypdf extraction follows the content-stream order, which mixes the two columns
of many conference papers line by line. Instead, every text fragment is collected
with its position, lines are rebuilt from the coordinates, and two-column pages are
read column by column. Running headers and footers (journal names, page numbers)
are removed by spotting lines that repeat at the top or bottom of many pages.
"""

from __future__ import annotations

import io
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from pypdf import PageObject, PdfReader
from pypdf.errors import PyPdfError

from ghostcite.config import INGEST, IngestConfig
from ghostcite.errors import InputError, ScannedPdfError
from ghostcite.ingest.sections import find_reference_section
from ghostcite.parse.cleanup import clean_text
from ghostcite.parse.split import SourceLine

PDF_MAGIC = b"%PDF-"

_LINE_TOLERANCE_PT = 2.0
"""Fragments whose baselines differ by less than this belong to the same line."""
_CHAR_WIDTH_EM = 0.5
"""Average glyph width as a fraction of the font size, used to estimate fragment width."""
_COLUMN_GUTTER_FRACTION = 0.04
_MIN_RIGHT_COLUMN_SHARE = 0.25
_MAX_SPANNING_SHARE = 0.10
_EDGE_LINES = 2
"""How many lines at the top and bottom of a page can be running headers or footers."""
_MIN_REPEAT_SHARE = 0.5
_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class _Fragment:
    x: float
    y: float
    width: float
    text: str


def has_pdf_magic(data: bytes) -> bool:
    """True when the bytes start like a PDF file (whitespace before the marker is tolerated)."""
    return data[:1024].lstrip().startswith(PDF_MAGIC)


def _fragments(page: PageObject) -> list[_Fragment]:
    fragments: list[_Fragment] = []

    def visit(
        text: str, cm: Sequence[float], tm: Sequence[float], _font: object, size: float
    ) -> None:
        if not text.strip():
            return
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        scale = abs(tm[0] * cm[0]) or 1.0
        for offset, piece in enumerate(text.split("\n")):
            if piece.strip():
                width = len(piece) * size * scale * _CHAR_WIDTH_EM
                fragments.append(_Fragment(x, y - offset * size, width, piece))

    page.extract_text(visitor_text=visit)
    return fragments


def _group_lines(fragments: Sequence[_Fragment]) -> list[list[_Fragment]]:
    lines: list[list[_Fragment]] = []
    for fragment in sorted(fragments, key=lambda f: (-f.y, f.x)):
        if lines and abs(lines[-1][0].y - fragment.y) <= _LINE_TOLERANCE_PT:
            lines[-1].append(fragment)
        else:
            lines.append([fragment])
    return [sorted(line, key=lambda f: f.x) for line in lines]


def _line_text(fragments: Sequence[_Fragment]) -> str:
    return " ".join(f.text.strip() for f in fragments)


def _is_two_column(fragments: Sequence[_Fragment], page_width: float) -> bool:
    middle = page_width / 2
    gutter = page_width * _COLUMN_GUTTER_FRACTION
    left = [f for f in fragments if f.x < middle - gutter]
    right = [f for f in fragments if f.x >= middle - gutter]
    if not left or len(right) < _MIN_RIGHT_COLUMN_SHARE * len(fragments):
        return False
    spanning = [f for f in left if f.x + f.width > middle + gutter]
    return len(spanning) <= _MAX_SPANNING_SHARE * len(left)


def page_lines(page: PageObject) -> list[str]:
    """Text lines of one page in reading order (column by column on two-column pages)."""
    fragments = _fragments(page)
    if not fragments:
        return []
    width = float(page.mediabox.width)
    if _is_two_column(fragments, width):
        middle = width / 2 - width * _COLUMN_GUTTER_FRACTION
        columns = (
            [f for f in fragments if f.x < middle],
            [f for f in fragments if f.x >= middle],
        )
        return [_line_text(line) for column in columns for line in _group_lines(column)]
    return [_line_text(line) for line in _group_lines(fragments)]


def _edge_key(line: str) -> str:
    """Normalize a header/footer line so "Page 3" and "Page 4" compare equal."""
    return re.sub(r"\d+", "#", line.lower()).strip()


def remove_running_lines(pages: Sequence[list[str]]) -> list[list[str]]:
    """Drop page numbers and headers/footers that repeat across pages."""
    counts: Counter[str] = Counter()
    for lines in pages:
        edges = {_edge_key(line) for line in lines[:_EDGE_LINES] + lines[-_EDGE_LINES:]}
        counts.update(edges)
    threshold = max(2, _MIN_REPEAT_SHARE * len(pages))
    repeated = {key for key, count in counts.items() if count >= threshold}

    cleaned: list[list[str]] = []
    for lines in pages:
        last = len(lines) - 1
        kept = []
        for i, line in enumerate(lines):
            at_edge = i < _EDGE_LINES or i > last - _EDGE_LINES
            if at_edge and (_PAGE_NUMBER.match(line) or _edge_key(line) in repeated):
                continue
            kept.append(line)
        cleaned.append(kept)
    return cleaned


def _open(data: bytes) -> PdfReader:
    if not has_pdf_magic(data):
        raise InputError("This file is not a PDF (it does not start with the %PDF- marker).")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise InputError("This PDF is password-protected. Remove the password and try again.")
        _ = len(reader.pages)
    except (PyPdfError, ValueError, KeyError, TypeError) as exc:
        raise InputError(f"This PDF could not be read; it may be damaged ({exc}).") from exc
    return reader


def pdf_text_pages(data: bytes, cfg: IngestConfig = INGEST) -> list[list[str]]:
    """Extract cleaned text lines for every page, raising a friendly error for scans."""
    reader = _open(data)
    if len(reader.pages) > cfg.max_pdf_pages:
        raise InputError(
            f"This PDF has {len(reader.pages)} pages; the limit is {cfg.max_pdf_pages}."
        )
    try:
        pages = [[clean_text(line) for line in page_lines(page)] for page in reader.pages]
    except (PyPdfError, ValueError, KeyError, TypeError) as exc:
        raise InputError(f"Text could not be extracted from this PDF ({exc}).") from exc
    characters = sum(len(line) for lines in pages for line in lines)
    if characters < cfg.min_text_chars_per_page * max(1, len(pages)):
        raise ScannedPdfError(
            "This PDF has no extractable text; it looks like a scanned image. GhostCite "
            "does not run OCR. Use the original digital PDF, a .bib file, or paste the "
            "references as text."
        )
    return remove_running_lines(pages)


def pdf_lines(data: bytes, cfg: IngestConfig = INGEST) -> list[SourceLine]:
    """Return the lines of the PDF's reference section."""
    lines = [SourceLine(line) for page in pdf_text_pages(data, cfg) for line in page]
    section = find_reference_section(lines)
    if section is None:
        raise InputError(
            "No References, Bibliography or Works Cited heading was found in this PDF. "
            "Paste the reference list as text instead."
        )
    return section
