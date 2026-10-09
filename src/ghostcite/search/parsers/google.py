"""Parse Google web results (``engine=google``), used only as a fallback for books and theses.

Web results have no structured authors or venue. A candidate carries the page title,
link, snippet and site, plus a best-effort year taken from the result date or the
snippet. Because of that, the matcher caps the confidence of Google-only matches
(``MatchConfig.fallback_confidence_cap``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from ghostcite.models import Candidate, Engine
from ghostcite.search.parsers import as_dict, as_list, as_str

_YEAR = re.compile(r"\b((?:1[89]|20)\d{2})\b")
# Site names appended to page titles: "Wings of Fire - Wikipedia", "... | Amazon.in".
# A colon is not a separator: it usually introduces a subtitle that belongs to the title.
_SITE_SUFFIX = re.compile(r"\s+[-|\u2013\u2014]\s+(?P<site>[^-|\u2013\u2014:]{1,40})$")
_MAX_SITE_WORDS = 4
# Knowledge Graph fields that hold a publication date, most specific first.
_KG_DATE_KEYS = ("originally_published", "publication_date", "first_published", "published", "date")
_TRAILING_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|\u2026)$")


def clean_title(title: str) -> str:
    """Remove a trailing site name and ellipsis that Google adds to page titles."""
    title = _TRAILING_ELLIPSIS.sub("", title.strip())
    match = _SITE_SUFFIX.search(title)
    if match and len(match.group("site").split()) <= _MAX_SITE_WORDS:
        title = title[: match.start()]
    return title.strip()


def _source(result: Mapping[str, Any]) -> str | None:
    source = as_str(result.get("source"))
    if source:
        return source
    link = as_str(result.get("link"))
    return urlparse(link).hostname if link else None


def _first_year(texts: list[str | None], current_year: int) -> int | None:
    for text in texts:
        for match in _YEAR.finditer(text or ""):
            year = int(match.group(1))
            if year <= current_year + 1:
                return year
    return None


def knowledge_graph_candidate(
    response: Mapping[str, Any], query: str, current_year: int
) -> Candidate | None:
    """Build a candidate from Google's Knowledge Graph panel, when there is one.

    For books the panel carries structured ``authors`` and a publication date
    (``originally_published`` in recorded responses), which is far better evidence than a
    web snippet.
    """
    graph = as_dict(response.get("knowledge_graph"))
    title = as_str(graph.get("title"))
    if title is None:
        return None
    authors_text = as_str(graph.get("authors")) or as_str(graph.get("author")) or ""
    authors = tuple(name.strip() for name in authors_text.split(",") if name.strip())
    year = _first_year([as_str(graph.get(key)) for key in _KG_DATE_KEYS], current_year)
    source = as_dict(graph.get("source"))
    return Candidate(
        engine=Engine.GOOGLE,
        title=title,
        link=as_str(source.get("link")),
        authors=authors,
        year=year,
        source="Google Knowledge Graph",
        snippet=as_str(graph.get("description")),
        query=query,
    )


def parse_google(
    response: Mapping[str, Any], query: str, *, current_year: int | None = None
) -> list[Candidate]:
    """Convert the Knowledge Graph panel (if any) and web ``organic_results`` into candidates."""
    year_now = current_year or datetime.now(tz=UTC).year
    graph_candidate = knowledge_graph_candidate(response, query, year_now)
    candidates: list[Candidate] = [graph_candidate] if graph_candidate else []
    for item in as_list(response.get("organic_results")):
        result = as_dict(item)
        title = as_str(result.get("title"))
        if title is None:
            continue
        candidates.append(
            Candidate(
                engine=Engine.GOOGLE,
                title=clean_title(title) or title,
                link=as_str(result.get("link")),
                year=_first_year(
                    [as_str(result.get("date")), as_str(result.get("snippet"))], year_now
                ),
                source=_source(result),
                snippet=as_str(result.get("snippet")),
                query=query,
            )
        )
    return candidates
