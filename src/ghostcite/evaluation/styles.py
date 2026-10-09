"""Render dataset rows as raw reference strings in common styles, and as BibTeX.

The evaluation feeds GhostCite text exactly as authors write it, so the parser is
tested end to end. Styles are assigned with a fixed seed, so every run sees the same
strings. The BibTeX rendering of the same rows measures matching without parsing noise.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from enum import StrEnum

from ghostcite.evaluation.dataset import EvalRow

BOOK_TYPES = frozenset({"book", "phdthesis", "techreport"})


class Style(StrEnum):
    """Reference styles used in the evaluation."""

    APA = "apa"
    IEEE = "ieee"
    VANCOUVER = "vancouver"
    INDIAN = "indian"
    """Common in Indian commerce and management journals.

    ``Surname, I.K. and Surname, I.K. (Year), "Title", Journal, Vol. X No. Y, pp. a-b.``
    """


def _initials(given: str, *, dots: bool = True, spaced: bool = True) -> str:
    parts = [p for p in given.replace(".", " ").replace("-", " ").split() if p]
    letters = [p[0].upper() for p in parts]
    if not dots:
        return "".join(letters)
    joiner = " " if spaced else ""
    return joiner.join(f"{letter}." for letter in letters)


def _is_book(row: EvalRow) -> bool:
    return row.entry_type in BOOK_TYPES


def _apa(row: EvalRow) -> str:
    names = [f"{family}, {_initials(given)}" for family, given in row.authors]
    authors = names[0] if len(names) == 1 else ", ".join(names[:-1]) + ", & " + names[-1]
    if _is_book(row):
        return f"{authors} ({row.year}). {row.title}. {row.venue}."
    details = f", {row.volume}" if row.volume else ""
    details += f"({row.issue})" if row.issue and row.volume else ""
    details += f", {row.pages}" if row.pages else ""
    doi = f" https://doi.org/{row.doi}" if row.doi else ""
    return f"{authors} ({row.year}). {row.title}. {row.venue}{details}.{doi}"


def _ieee(row: EvalRow) -> str:
    names = [f"{_initials(given)} {family}" for family, given in row.authors]
    if len(names) <= 2:
        authors = " and ".join(names)
    else:
        authors = ", ".join(names[:-1]) + ", and " + names[-1]
    if _is_book(row):
        return f"{authors}, {row.title}. {row.venue}, {row.year}."
    parts = [f"{authors}, “{row.title},” {row.venue}"]
    if row.volume:
        parts.append(f"vol. {row.volume}")
    if row.issue:
        parts.append(f"no. {row.issue}")
    if row.pages:
        parts.append(f"pp. {row.pages}")
    parts.append(str(row.year))
    return ", ".join(parts) + "."


def _vancouver(row: EvalRow) -> str:
    authors = ", ".join(f"{family} {_initials(given, dots=False)}" for family, given in row.authors)
    if _is_book(row):
        return f"{authors}. {row.title}. {row.venue}; {row.year}."
    volume = f";{row.volume}" if row.volume else ""
    issue = f"({row.issue})" if row.issue and row.volume else ""
    pages = f":{row.pages}" if row.pages else ""
    return f"{authors}. {row.title}. {row.venue}. {row.year}{volume}{issue}{pages}."


def _indian(row: EvalRow) -> str:
    names = [f"{family}, {_initials(given, spaced=False)}" for family, given in row.authors]
    authors = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    if _is_book(row):
        return f"{authors} ({row.year}), {row.title}, {row.venue}."
    details = f", Vol. {row.volume}" if row.volume else ""
    details += f" No. {row.issue}" if row.issue else ""
    details += f", pp. {row.pages}" if row.pages else ""
    return f'{authors} ({row.year}), "{row.title}", {row.venue}{details}.'


_RENDERERS = {
    Style.APA: _apa,
    Style.IEEE: _ieee,
    Style.VANCOUVER: _vancouver,
    Style.INDIAN: _indian,
}


def render(row: EvalRow, style: Style) -> str:
    """The row as a reference string in ``style``."""
    return _RENDERERS[style](row)


def assign_styles(rows: Sequence[EvalRow], seed: int) -> dict[str, Style]:
    """A fixed, roughly even style assignment: shuffled ids dealt round-robin."""
    ids = sorted(row.id for row in rows)
    random.Random(seed).shuffle(ids)  # noqa: S311 - reproducible sampling, not security
    styles = list(Style)
    return {row_id: styles[i % len(styles)] for i, row_id in enumerate(ids)}


def _bibtex_value(value: str) -> str:
    return "{" + value.replace("{", "").replace("}", "") + "}"


def to_bibtex(rows: Sequence[EvalRow]) -> str:
    """All rows as one BibTeX file, keyed by row id."""
    entries = []
    for row in rows:
        venue_field = {
            "article": "journal",
            "inproceedings": "booktitle",
            "book": "publisher",
        }.get(row.entry_type, "howpublished")
        fields = {
            "title": row.title,
            "author": " and ".join(f"{family}, {given}" for family, given in row.authors),
            "year": str(row.year),
            venue_field: row.venue,
            "volume": row.volume,
            "number": row.issue,
            "pages": row.pages,
            "doi": row.doi,
        }
        body = ",\n".join(
            f"  {name} = {_bibtex_value(value)}" for name, value in fields.items() if value
        )
        entries.append(f"@{row.entry_type}{{{row.id},\n{body}\n}}")
    return "\n\n".join(entries) + "\n"
