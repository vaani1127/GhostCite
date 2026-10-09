"""Parse Google Scholar results (``engine=google_scholar``).

The useful metadata sits in ``publication_info.summary``, a single display string:

    "A Vaswani, N Shazeer, N Parmar… - Advances in neural …, 2017 - proceedings.neurips.cc"
     └──────────── authors ────────┘   └──── venue ────┘ year   └────── source ──────┘

Scholar truncates long author lists and venues with "…", so both carry a truncation flag
that the matcher takes into account.

On 2026-10-09 Scholar began serving a second layout, in which the parts are glued
together and the source follows a bullet:

    "FD DavisMIS quarterly, 1989•JSTOR"        "J Bhagwati1993•academic.oup.com"

In that layout ``publication_info.authors`` lists every displayed author (with or
without a Scholar profile), so the author prefix is removed exactly. Both layouts are
parsed; recorded examples of each are in ``tests/fixtures/serpapi``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ghostcite.models import Candidate, Engine
from ghostcite.search.parsers import as_dict, as_list, as_str

_SEPARATOR = re.compile(r"\s+[-\u2010-\u2014]\s+")
_YEAR_AT_END = re.compile(r"(?:^|,\s*)((?:1[89]|20)\d{2})\s*$")
_HOST = re.compile(r"^[\w-]+(?:\.[\w-]+)+$")
_ELLIPSIS = ("\u2026", "...")
_BULLET = "\u2022"
# Where glued text switches from an author's surname to the venue ("DavisMIS").
_GLUE = re.compile(r"(?<=[a-z\u00df-\u00ff])(?=[A-Z\u00c0-\u00de])")
_YEAR_GLUED = re.compile(r"(?:,\s*)?((?:1[89]|20)\d{2})\s*$")
_TITLE_TAG = re.compile(r"^\[(?:PDF|HTML|BOOK|B|CITATION|C)\]\s*", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Summary:
    """The pieces of a Scholar ``publication_info.summary`` string."""

    authors: tuple[str, ...]
    authors_truncated: bool
    venue: str | None
    venue_truncated: bool
    year: int | None
    source: str | None


def _strip_ellipsis(text: str) -> tuple[str, bool]:
    """Remove leading and trailing ellipses ("... of the IEEE conference ...")."""
    truncated = False
    for mark in _ELLIPSIS:
        if text.startswith(mark):
            text, truncated = text[len(mark) :].lstrip(), True
        if text.endswith(mark):
            text, truncated = text[: -len(mark)].rstrip(" ,"), True
    return text, truncated


def _split_authors(part: str) -> tuple[tuple[str, ...], bool]:
    part, truncated = _strip_ellipsis(part.strip())
    names = tuple(name.strip() for name in part.split(",") if name.strip())
    return names, truncated


def _split_glued(head: str, names: Sequence[str]) -> tuple[str, str]:
    """Separate the author list from the venue in a glued bullet-layout head."""
    listed = ", ".join(names)
    if listed and head.startswith(listed):
        rest = head[len(listed) :]
        for mark in _ELLIPSIS:
            if rest.startswith(mark):  # "T Yu\u2026The lancet": the ellipsis cuts the author list
                return listed + mark, rest[len(mark) :]
        return listed, rest
    for mark in _ELLIPSIS:
        if mark in head:
            index = head.index(mark) + len(mark)
            return head[:index], head[index:]
    junction = _GLUE.search(head)
    if junction is None:
        return head, ""
    return head[: junction.start()], head[junction.start() :]


def _parse_bullet(summary: str, names: Sequence[str]) -> Summary:
    head, _, source = summary.rpartition(_BULLET)
    year = None
    year_match = _YEAR_GLUED.search(head)
    if year_match:
        year = int(year_match.group(1))
        head = head[: year_match.start()]
    authors_part, venue_part = _split_glued(head.strip(), names)
    venue, venue_truncated = _strip_ellipsis(venue_part.strip(" ,"))
    authors, authors_truncated = _split_authors(authors_part)
    return Summary(
        authors=authors,
        authors_truncated=authors_truncated,
        venue=venue or None,
        venue_truncated=venue_truncated,
        year=year,
        source=source.strip() or None,
    )


def parse_summary(summary: str, names: Sequence[str] = ()) -> Summary:
    """Split a Scholar summary into authors, venue, year and source host.

    ``names`` are the structured ``publication_info.authors`` names; the bullet layout
    needs them to find where the author list ends.
    """
    summary = summary.replace("\u00a0", " ")
    if _BULLET in summary:
        return _parse_bullet(summary, names)
    segments = [s.strip() for s in _SEPARATOR.split(summary) if s.strip()]
    source = None
    if len(segments) >= 3 or (len(segments) == 2 and _HOST.match(segments[-1])):
        source = segments.pop()

    authors_part, middle = "", ""
    if len(segments) >= 2:
        authors_part, middle = segments[0], " - ".join(segments[1:])
    elif segments:
        # One segment: venue/year if it ends in a year ("Nature, 2015"), else authors.
        if _YEAR_AT_END.search(segments[0]):
            middle = segments[0]
        else:
            authors_part = segments[0]

    year = None
    year_match = _YEAR_AT_END.search(middle)
    if year_match:
        year = int(year_match.group(1))
        middle = middle[: year_match.start()]
    venue, venue_truncated = _strip_ellipsis(middle.strip(" ,"))
    authors, authors_truncated = _split_authors(authors_part)
    return Summary(
        authors=authors,
        authors_truncated=authors_truncated,
        venue=venue or None,
        venue_truncated=venue_truncated,
        year=year,
        source=source,
    )


def _inline_total(result: Mapping[str, Any], link: str) -> int | None:
    """``inline_links.<link>.total`` as a non-negative int (``cited_by`` or ``versions``)."""
    total = as_dict(as_dict(result.get("inline_links")).get(link)).get("total")
    return total if isinstance(total, int) and not isinstance(total, bool) and total >= 0 else None


def parse_scholar(response: Mapping[str, Any], query: str) -> list[Candidate]:
    """Convert ``organic_results`` into candidates, skipping entries without a title."""
    candidates: list[Candidate] = []
    for item in as_list(response.get("organic_results")):
        result = as_dict(item)
        title = as_str(result.get("title"))
        if title is None:
            continue
        info = as_dict(result.get("publication_info"))
        names = [
            name
            for author in as_list(info.get("authors"))
            if (name := as_str(as_dict(author).get("name")))
        ]
        summary = parse_summary(as_str(info.get("summary")) or "", names)
        candidates.append(
            Candidate(
                engine=Engine.GOOGLE_SCHOLAR,
                title=_TITLE_TAG.sub("", title),
                link=as_str(result.get("link")),
                result_id=as_str(result.get("result_id")),
                authors=summary.authors,
                authors_truncated=summary.authors_truncated,
                year=summary.year,
                venue=summary.venue,
                venue_truncated=summary.venue_truncated,
                source=summary.source,
                snippet=as_str(result.get("snippet")),
                cited_by=_inline_total(result, "cited_by"),
                versions=_inline_total(result, "versions"),
                query=query,
            )
        )
    return candidates
