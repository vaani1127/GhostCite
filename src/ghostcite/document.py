"""Turn an uploaded file or pasted text into a list of parsed references.

This is the boundary where untrusted input enters GhostCite. Size limits are enforced
here, and the file type is decided by content (magic bytes, BibTeX syntax), never by
the extension alone.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePath

from ghostcite.config import INGEST, IngestConfig
from ghostcite.errors import InputError
from ghostcite.ingest.bibtex import parse_bibtex
from ghostcite.ingest.pdf import has_pdf_magic, pdf_lines
from ghostcite.ingest.text import decode_text, text_lines
from ghostcite.models import Reference, SourceFormat
from ghostcite.parse.fields import parse_fields
from ghostcite.parse.split import SourceLine, split_references

_BIBTEX_ENTRY = re.compile(r"^\s*@\s*[A-Za-z]+\s*[{(]", re.MULTILINE)
_ZIP_MAGIC = b"PK\x03\x04"
_MAX_NAME_CHARS = 120
PASTED_TEXT_NAME = "pasted-text"


@dataclass(frozen=True, slots=True)
class Document:
    """References extracted from one input, ready to be checked."""

    source_name: str
    source_format: SourceFormat
    references: tuple[Reference, ...]
    warnings: tuple[str, ...] = ()


def safe_source_name(filename: str | None) -> str:
    """Return the base file name only.

    A full path often contains the user's name, so it must never reach a report.
    """
    if not filename:
        return PASTED_TEXT_NAME
    name = PurePath(filename.replace("\\", "/")).name.strip()
    return name[:_MAX_NAME_CHARS] or PASTED_TEXT_NAME


def detect_format(data: bytes, filename: str | None = None) -> SourceFormat:
    """Decide how to read ``data``, by content first and by extension only to break ties."""
    suffix = PurePath(filename or "").suffix.lower()
    if has_pdf_magic(data):
        return SourceFormat.PDF
    if suffix == ".pdf":
        raise InputError("This file has a .pdf name but is not a PDF document.")
    if data.startswith(_ZIP_MAGIC):
        raise InputError(
            "Word, OpenDocument and other zipped formats are not supported. "
            "Export the document as PDF, or paste its references as text."
        )
    text = decode_text(data)
    if suffix == ".bib" or _BIBTEX_ENTRY.search(text):
        return SourceFormat.BIBTEX
    return SourceFormat.TEXT


def _references_from_lines(
    lines: Sequence[SourceLine], source_format: SourceFormat
) -> list[Reference]:
    return [
        Reference(
            index=index,
            raw=raw.text,
            source_format=source_format,
            line=raw.line,
            fields=parse_fields(raw.text),
        )
        for index, raw in enumerate(split_references(lines), 1)
    ]


def _finish(
    name: str,
    source_format: SourceFormat,
    references: list[Reference],
    warnings: list[str],
    cfg: IngestConfig,
) -> Document:
    if not references:
        raise InputError(
            "No references were found. Check that the input contains a reference list "
            "(numbered like [1] or 1., or one reference per line)."
        )
    if len(references) > cfg.max_references:
        raise InputError(
            f"Found {len(references)} references; the limit is {cfg.max_references} per document."
        )
    return Document(name, source_format, tuple(references), tuple(warnings))


def load_document(data: bytes, filename: str | None = None, cfg: IngestConfig = INGEST) -> Document:
    """Read references from the bytes of an uploaded PDF, BibTeX or text file."""
    if not data.strip():
        raise InputError("The input is empty.")
    if len(data) > cfg.max_input_bytes:
        limit_mib = cfg.max_input_bytes // (1024 * 1024)
        raise InputError(f"The file is larger than the {limit_mib} MiB limit.")
    name = safe_source_name(filename)
    source_format = detect_format(data, filename)
    if source_format is SourceFormat.PDF:
        references = _references_from_lines(pdf_lines(data, cfg), SourceFormat.PDF)
        return _finish(name, source_format, references, [], cfg)
    text = decode_text(data)
    if source_format is SourceFormat.BIBTEX:
        result = parse_bibtex(text)
        return _finish(name, source_format, result.references, result.warnings, cfg)
    references = _references_from_lines(text_lines(text), SourceFormat.TEXT)
    return _finish(name, source_format, references, [], cfg)


def load_text(text: str, cfg: IngestConfig = INGEST) -> Document:
    """Read references from pasted text (plain reference list or BibTeX)."""
    return load_document(text.encode("utf-8"), None, cfg)
