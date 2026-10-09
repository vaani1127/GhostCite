"""Check the evaluation ground truth against Crossref and arXiv (never against SerpApi).

* A **real** row passes when its DOI (Crossref) or arXiv ID (arXiv API) resolves to a
  record whose title, first-author surname and year agree with the row.
* A **perturbed** row passes when its source row passed.
* An **invented** row passes when Crossref's bibliographic search finds nothing with a
  similar title, which is evidence that the work does not exist.

Rows that fail are excluded from the evaluation. Network access is injected (``fetch``),
so the logic is tested offline with recorded API responses.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree

from ghostcite.evaluation.dataset import EvalRow, Kind, Perturbation
from ghostcite.match.normalize import surname_key
from ghostcite.match.score import is_title_match, title_similarity

Fetch = Callable[[str], str]
"""Returns the body of an HTTP GET for a URL."""

CROSSREF_WORK = "https://api.crossref.org/works/{doi}"
CROSSREF_SEARCH = "https://api.crossref.org/works?{query}"
ARXIV_QUERY = "https://export.arxiv.org/api/query?id_list={arxiv_id}"
_ATOM = {"atom": "http://www.w3.org/2005/Atom"}
_YEAR_TOLERANCE = 1
"""Crossref "issued" can be the online-first year, one before the print issue."""
_INVENTED_MAX_SIMILARITY = 0.8
"""A Crossref hit this similar to an invented title would mean it might exist after all."""
_TAGS = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class Record:
    """Canonical metadata of a work from Crossref or arXiv."""

    title: str
    first_author: str
    year: int | None
    source: str


@dataclass(frozen=True, slots=True)
class Validation:
    """Outcome for one row."""

    ok: bool
    problems: tuple[str, ...] = ()
    record: Record | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


def _crossref_record(message: dict[str, Any]) -> Record:
    titles = message.get("title") or [""]
    authors = message.get("author") or message.get("editor") or [{}]
    parts = (message.get("issued") or {}).get("date-parts") or [[None]]
    year = parts[0][0] if parts and parts[0] else None
    return Record(
        title=_TAGS.sub("", str(titles[0])).strip(),
        first_author=str(authors[0].get("family") or authors[0].get("name") or ""),
        year=int(year) if isinstance(year, int) else None,
        source="crossref",
    )


def _arxiv_record(atom: str) -> Record:
    root = ElementTree.fromstring(atom)  # noqa: S314 - arXiv's own API response, not user input
    entry = root.find("atom:entry", _ATOM)
    if entry is None:
        raise LookupError("arXiv returned no entry")
    title = " ".join((entry.findtext("atom:title", "", _ATOM) or "").split())
    author = entry.findtext("atom:author/atom:name", "", _ATOM) or ""
    published = entry.findtext("atom:published", "", _ATOM) or ""
    if not title or title.lower() == "error":
        raise LookupError("arXiv has no record with this ID")
    return Record(
        title=title,
        first_author=author.split()[-1] if author else "",
        year=int(published[:4]) if published[:4].isdigit() else None,
        source="arxiv",
    )


def fetch_record(row: EvalRow, fetch: Fetch) -> Record:
    """Look the row up by DOI (Crossref) or arXiv ID."""
    if row.doi:
        payload = json.loads(fetch(CROSSREF_WORK.format(doi=urllib.parse.quote(row.doi, safe="/"))))
        return _crossref_record(payload["message"])
    if row.arxiv_id:
        return _arxiv_record(fetch(ARXIV_QUERY.format(arxiv_id=row.arxiv_id)))
    raise LookupError(f"{row.id} has no identifier")


def compare(row: EvalRow, record: Record) -> list[str]:
    """Differences between the row and the canonical record (empty when they agree)."""
    problems = []
    if (
        not is_title_match(row.title, record.title)
        and title_similarity(row.title, record.title) < 0.9
    ):
        problems.append(f"title differs: registry has {record.title!r}")
    if surname_key(row.authors[0][0]) != surname_key(record.first_author):
        problems.append(f"first author differs: registry has {record.first_author!r}")
    if record.year is None or abs(record.year - row.year) > _YEAR_TOLERANCE:
        problems.append(f"year differs: registry has {record.year}")
    return problems


def validate_real(row: EvalRow, fetch: Fetch) -> Validation:
    """Resolve a real row's identifier and compare it with the row."""
    try:
        record = fetch_record(row, fetch)
    except (LookupError, ValueError, KeyError, OSError) as exc:
        return Validation(ok=False, problems=(f"lookup failed: {exc}",))
    problems = compare(row, record)
    notes = () if record.year == row.year else (f"registry year {record.year}",)
    return Validation(ok=not problems, problems=tuple(problems), record=record, notes=notes)


def validate_invented(row: EvalRow, fetch: Fetch) -> Validation:
    """An invented title must have no close match in Crossref's bibliographic search."""
    query = urllib.parse.urlencode(
        {"query.bibliographic": row.title, "rows": 5, "select": "title,DOI"}
    )
    try:
        items = json.loads(fetch(CROSSREF_SEARCH.format(query=query)))["message"]["items"]
    except (ValueError, KeyError, OSError) as exc:
        return Validation(ok=False, problems=(f"search failed: {exc}",))
    titles = [_TAGS.sub("", str((item.get("title") or [""])[0])) for item in items]
    closest = max((title_similarity(row.title, t) for t in titles), default=0.0)
    if closest >= _INVENTED_MAX_SIMILARITY:
        return Validation(
            ok=False, problems=(f"a similar title exists in Crossref ({closest:.2f})",)
        )
    return Validation(ok=True, notes=(f"closest Crossref title similarity {closest:.2f}",))


def validate_rows(rows: Sequence[EvalRow], fetch: Fetch) -> dict[str, Validation]:
    """Validate every row; perturbed rows inherit their source row's outcome."""
    results: dict[str, Validation] = {}
    for row in rows:
        if row.kind is Kind.REAL:
            results[row.id] = validate_real(row, fetch)
        elif row.perturbation is Perturbation.INVENTED:
            results[row.id] = validate_invented(row, fetch)
    for row in rows:
        if row.source is not None:
            parent = results.get(row.source)
            ok = parent is not None and parent.ok
            results[row.id] = Validation(
                ok=ok,
                problems=() if ok else (f"source row {row.source} did not validate",),
            )
    return results


def to_json(results: dict[str, Validation]) -> dict[str, Any]:
    """Serializable report written to ``eval/dataset_validation.json``."""
    return {
        row_id: {
            "ok": result.ok,
            "problems": list(result.problems),
            "notes": list(result.notes),
            "record": None
            if result.record is None
            else {
                "title": result.record.title,
                "first_author": result.record.first_author,
                "year": result.record.year,
                "source": result.record.source,
            },
        }
        for row_id, result in sorted(results.items())
    }
