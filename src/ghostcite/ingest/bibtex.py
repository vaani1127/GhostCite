"""BibTeX input, parsed with bibtexparser v2.

BibTeX is already structured, so no free-text heuristics run and every field that is
present gets full parse confidence. Malformed entries never abort the file. Each one
becomes an UNPARSEABLE reference that keeps its line number, so reports (and SARIF in
code review) can point at the exact line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bibtexparser import middlewares
from bibtexparser.entrypoint import parse_string
from bibtexparser.model import (
    DuplicateBlockKeyBlock,
    DuplicateFieldKeyBlock,
    Entry,
    ParsingFailedBlock,
)

from ghostcite.models import Author, ParseConfidence, ParsedFields, Reference, SourceFormat
from ghostcite.parse.cleanup import clean_text
from ghostcite.parse.fields import find_doi

_VENUE_FIELDS = ("journal", "booktitle", "school", "institution", "publisher", "howpublished")
_ENTRY_KEY = re.compile(r"@\s*\w+\s*[{(]\s*([^,\s]+)")
_YEAR = re.compile(r"\b(\d{4})\b")
_ET_AL_NAMES = frozenset({"others", "et al.", "et al"})


@dataclass(frozen=True, slots=True)
class BibtexResult:
    """References read from a BibTeX file plus human-readable warnings."""

    references: list[Reference]
    warnings: list[str]


def _text(value: object) -> str:
    """Flatten a field value into one clean line (BibTeX values often span lines)."""
    return " ".join(clean_text(str(value)).replace("{", "").replace("}", "").split())


def _authors(entry: Entry) -> tuple[tuple[Author, ...], bool]:
    field = entry.fields_dict.get("author") or entry.fields_dict.get("editor")
    if field is None or not isinstance(field.value, list):
        return (), False
    authors: list[Author] = []
    et_al = False
    for name in field.value:
        if not isinstance(name, middlewares.NameParts):
            continue
        surname = _text(" ".join([*name.von, *name.last]))
        if surname.lower() in _ET_AL_NAMES:
            et_al = True
        elif surname:
            authors.append(Author(surname=surname, given=_text(" ".join(name.first))))
    return tuple(authors), et_al


def _year(entry: Entry) -> int | None:
    for key in ("year", "date"):
        field = entry.fields_dict.get(key)
        if field is not None:
            match = _YEAR.search(str(field.value))
            if match:
                return int(match.group(1))
    return None


def _field(entry: Entry, *keys: str) -> str | None:
    for key in keys:
        field = entry.fields_dict.get(key)
        if field is not None:
            text = _text(field.value)
            if text:
                return text
    return None


def entry_fields(entry: Entry) -> ParsedFields:
    """Map one BibTeX entry onto :class:`ParsedFields`."""
    title = _field(entry, "title")
    authors, et_al = _authors(entry)
    year = _year(entry)
    venue = _field(entry, *_VENUE_FIELDS)
    doi_field = _field(entry, "doi")
    doi = find_doi(doi_field) if doi_field else None
    return ParsedFields(
        title=title,
        authors=authors,
        et_al=et_al,
        year=year,
        venue=venue,
        doi=doi,
        entry_type=entry.entry_type.lower(),
        confidence=ParseConfidence(
            title=1.0 if title else 0.0,
            authors=1.0 if authors else 0.0,
            year=1.0 if year else 0.0,
            venue=1.0 if venue else 0.0,
            doi=1.0 if doi else 0.0,
        ),
    )


def _failure_warning(block: ParsingFailedBlock, line: int | None, key: str | None) -> str:
    if isinstance(block, DuplicateBlockKeyBlock):
        return f"Line {line}: duplicate citation key '{key}'; both entries are checked."
    if isinstance(block, DuplicateFieldKeyBlock):
        return f"Line {line}: entry '{key}' repeats a field; only one of the values is used."
    return f"Line {line}: entry could not be parsed (BibTeX syntax error); marked UNPARSEABLE."


def parse_bibtex(text: str) -> BibtexResult:
    """Parse BibTeX source into references, keeping malformed entries as unparseable."""
    library = parse_string(
        text,
        append_middleware=[
            middlewares.LatexDecodingMiddleware(),
            middlewares.SeparateCoAuthors(),
            middlewares.SplitNameParts(),
        ],
    )
    references: list[Reference] = []
    warnings: list[str] = []
    for block in library.blocks:
        if not isinstance(block, Entry | ParsingFailedBlock):
            continue  # @string, @preamble and comments carry no reference
        line = block.start_line + 1 if block.start_line is not None else None
        raw = block.raw or ""
        entry = block if isinstance(block, Entry) else _recovered_entry(block)
        key = entry.key if entry is not None else _key_from_raw(raw)
        if isinstance(block, ParsingFailedBlock):
            warnings.append(_failure_warning(block, line, key))
        references.append(
            Reference(
                index=len(references) + 1,
                raw=_text(raw),
                source_format=SourceFormat.BIBTEX,
                key=key,
                line=line,
                fields=entry_fields(entry) if entry is not None else ParsedFields(),
            )
        )
    return BibtexResult(references=references, warnings=warnings)


def _recovered_entry(block: ParsingFailedBlock) -> Entry | None:
    """The usable entry behind a duplicate-key/field failure; ``None`` for syntax errors."""
    recovered = block.ignore_error_block
    return recovered if isinstance(recovered, Entry) else None


def _key_from_raw(raw: str) -> str | None:
    match = _ENTRY_KEY.search(raw)
    return match.group(1) if match else None
