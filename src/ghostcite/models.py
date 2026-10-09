"""Domain models shared by every stage of the GhostCite pipeline.

All models are immutable (``frozen``) so a value produced by one stage cannot be
changed behind the back of a later stage, and unknown fields are rejected so typos in
construction fail loudly instead of silently dropping data.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    """Base class: immutable, strict about unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Verdict(StrEnum):
    """Outcome of checking one reference."""

    VERIFIED = "VERIFIED"
    """A Scholar record matches the title and no checked field conflicts."""
    METADATA_MISMATCH = "METADATA_MISMATCH"
    """The paper exists, but authors, year or venue differ from the citation."""
    NOT_FOUND = "NOT_FOUND"
    """No search result is close enough to the cited title: a likely fabrication."""
    UNPARSEABLE = "UNPARSEABLE"
    """No usable title could be extracted, so no search was spent."""
    SKIPPED_BUDGET = "SKIPPED_BUDGET"
    """The credit budget ran out before this reference was searched."""


class SourceFormat(StrEnum):
    """Kind of document the references were read from."""

    PDF = "pdf"
    BIBTEX = "bibtex"
    TEXT = "text"


class Engine(StrEnum):
    """SerpApi engines used by the query planner."""

    GOOGLE_SCHOLAR = "google_scholar"
    GOOGLE = "google"


class FieldName(StrEnum):
    """Citation fields that are parsed and compared."""

    TITLE = "title"
    AUTHORS = "authors"
    YEAR = "year"
    VENUE = "venue"
    DOI = "doi"


class FieldStatus(StrEnum):
    """Result of comparing one cited field with the matching candidate."""

    MATCH = "match"
    PARTIAL = "partial"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"
    """One side is missing the field, so it cannot be judged."""


class RunMode(StrEnum):
    """Where search results came from during a run."""

    LIVE = "live"
    OFFLINE = "offline"
    DEMO = "demo"


class Author(_Frozen):
    """One cited author, reduced to what can be reliably compared."""

    surname: str = Field(min_length=1)
    given: str = ""
    """Given names or initials as written, e.g. ``"A. K."`` or ``"Ashish"``."""


class ParseConfidence(_Frozen):
    """How sure the parser is about each extracted field, each in [0, 1]."""

    title: float = Field(default=0.0, ge=0.0, le=1.0)
    authors: float = Field(default=0.0, ge=0.0, le=1.0)
    year: float = Field(default=0.0, ge=0.0, le=1.0)
    venue: float = Field(default=0.0, ge=0.0, le=1.0)
    doi: float = Field(default=0.0, ge=0.0, le=1.0)


class ParsedFields(_Frozen):
    """Structured fields extracted from one raw reference."""

    title: str | None = None
    authors: tuple[Author, ...] = ()
    et_al: bool = False
    """True when the citation abbreviates the author list ("et al.")."""
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    entry_type: str | None = None
    """BibTeX entry type (``article``, ``book``, ``phdthesis`` …) when known."""
    confidence: ParseConfidence = ParseConfidence()


class Reference(_Frozen):
    """One reference as found in the input document."""

    index: int = Field(ge=1)
    """1-based position in the document's reference list."""
    raw: str
    source_format: SourceFormat
    key: str | None = None
    """BibTeX citation key, when the input is BibTeX."""
    line: int | None = Field(default=None, ge=1)
    """1-based line where the reference starts, used for SARIF locations."""
    fields: ParsedFields


class Candidate(_Frozen):
    """One search result that might be the cited work."""

    engine: Engine
    title: str
    link: str | None = None
    result_id: str | None = None
    authors: tuple[str, ...] = ()
    """Author names as displayed by the engine, e.g. ``"A Vaswani"``."""
    authors_truncated: bool = False
    """Scholar shortens long author lists with an ellipsis."""
    year: int | None = None
    venue: str | None = None
    venue_truncated: bool = False
    source: str | None = None
    """Host or publisher shown with the result, e.g. ``"proceedings.neurips.cc"``."""
    snippet: str | None = None
    cited_by: int | None = Field(default=None, ge=0)
    versions: int | None = Field(default=None, ge=0)
    """How many versions (preprint, conference, journal ...) Scholar groups under this work."""
    query: str
    """The exact query string that produced this candidate."""


class FieldMatch(_Frozen):
    """Comparison of one field between the citation and a candidate."""

    field: FieldName
    status: FieldStatus
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    cited: str | None = None
    found: str | None = None


class MatchResult(_Frozen):
    """A candidate together with its per-field comparison and combined confidence."""

    candidate: Candidate
    fields: tuple[FieldMatch, ...]
    confidence: float = Field(ge=0.0, le=1.0)

    def field(self, name: FieldName) -> FieldMatch | None:
        """Return the comparison for ``name``, or ``None`` if it was not compared."""
        return next((f for f in self.fields if f.field is name), None)


class ReferenceResult(_Frozen):
    """Final, explainable outcome for one reference."""

    reference: Reference
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    best_match: MatchResult | None = None
    mismatched_fields: tuple[FieldName, ...] = ()
    queries: tuple[str, ...] = ()
    """Every query sent for this reference, in order (cached or live)."""
    searches_used: int = Field(default=0, ge=0)
    """Live SerpApi searches spent on this reference (cache hits are free)."""
    duplicate_of: int | None = None
    """Index of an earlier identical reference whose result was reused."""


class Summary(_Frozen):
    """Document-level totals."""

    total: int = Field(ge=0)
    counts: dict[Verdict, int]
    integrity_score: float | None = Field(default=None, ge=0.0, le=100.0)
    """See ``ghostcite.verdict.integrity_score``; ``None`` when nothing was checkable."""
    checked: int = Field(ge=0)
    """References that received a definitive verdict (verified, mismatch or not found)."""
    credits_used: int = Field(ge=0)
    cache_hits: int = Field(ge=0)


class Report(_Frozen):
    """Everything GhostCite knows about one checked document."""

    tool_version: str
    generated_at: datetime
    source_name: str
    """File name only (never a full path, which could contain personal data)."""
    source_format: SourceFormat
    mode: RunMode
    results: tuple[ReferenceResult, ...]
    summary: Summary
    warnings: tuple[str, ...] = ()
    """Non-fatal problems, e.g. BibTeX entries that failed to parse."""
