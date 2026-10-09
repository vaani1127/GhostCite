"""Decide which SerpApi searches to run for a reference, cheapest and most precise first.

The pipeline runs the planned queries in order and stops at the first confident match,
so a correct citation usually costs one credit:

1. **Google Scholar, exact title in quotes.** The most precise query. A real paper is
   almost always the top result, while a fabricated title typically returns nothing.
2. **Google Scholar, unquoted title plus ``author:`` first-author surname.** Recovers
   titles cited with typos, different punctuation or a dropped subtitle, which an
   exact-phrase search misses.
3. **Google web search, quoted title plus surname.** Only for books, theses and
   reports (``SearchConfig.fallback_entry_types``), which Scholar covers poorly. It is
   never run for journal or conference papers, so a fabricated paper costs at most
   two credits.

Year filters (``as_ylo``/``as_yhi``) are deliberately not used. They would hide exactly
the wrong-year citations GhostCite exists to catch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from ghostcite.config import SEARCH, SearchConfig
from ghostcite.models import Engine, ParsedFields


class Strategy(StrEnum):
    """Query strategies in the order they are tried."""

    SCHOLAR_EXACT_TITLE = "scholar_exact_title"
    SCHOLAR_TITLE_AUTHOR = "scholar_title_author"
    GOOGLE_FALLBACK = "google_fallback"


@dataclass(frozen=True, slots=True)
class PlannedQuery:
    """One search to run: the SerpApi parameters plus why it was chosen."""

    strategy: Strategy
    engine: Engine
    params: dict[str, str] = field(hash=False)

    @property
    def text(self) -> str:
        """The query string, as shown in reports."""
        return self.params["q"]


_QUOTES = re.compile(r"[\"\u201c\u201d\u00ab\u00bb]")


def _query_title(title: str, cfg: SearchConfig) -> str:
    """Title without quote characters, cut at a word boundary to ``max_query_chars``."""
    text = " ".join(_QUOTES.sub(" ", title).split())
    if len(text) <= cfg.max_query_chars:
        return text
    return text[: cfg.max_query_chars].rsplit(" ", 1)[0]


def _first_surname(fields: ParsedFields) -> str | None:
    """Last word of the first author's surname ("de la Fontaine" → "Fontaine")."""
    if not fields.authors:
        return None
    return fields.authors[0].surname.split()[-1]


def _scholar(strategy: Strategy, q: str, cfg: SearchConfig) -> PlannedQuery:
    params = {
        "engine": Engine.GOOGLE_SCHOLAR.value,
        "q": q,
        "hl": cfg.language,
        "num": str(cfg.results_per_query),
    }
    return PlannedQuery(strategy, Engine.GOOGLE_SCHOLAR, params)


def plan_queries(fields: ParsedFields, cfg: SearchConfig = SEARCH) -> list[PlannedQuery]:
    """Return the ordered queries for a reference; empty when there is no title to search."""
    if not fields.title:
        return []
    title = _query_title(fields.title, cfg)
    surname = _first_surname(fields)

    queries = [_scholar(Strategy.SCHOLAR_EXACT_TITLE, f'"{title}"', cfg)]
    author_filter = f' author:"{surname}"' if surname else ""
    queries.append(_scholar(Strategy.SCHOLAR_TITLE_AUTHOR, f"{title}{author_filter}", cfg))
    if fields.entry_type in cfg.fallback_entry_types:
        q = f'"{title}" {surname}' if surname else f'"{title}"'
        queries.append(
            PlannedQuery(
                Strategy.GOOGLE_FALLBACK,
                Engine.GOOGLE,
                {
                    "engine": Engine.GOOGLE.value,
                    "q": q,
                    "hl": cfg.language,
                    "gl": cfg.google_country,
                },
            )
        )
    return queries
