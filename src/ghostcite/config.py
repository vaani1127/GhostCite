"""Every tunable threshold, weight and limit in GhostCite, each with the reason for its value.

The values are grouped into frozen dataclasses. Functions take a config object as a
parameter (defaulting to the instances at the bottom of this module), so the evaluation
harness can try alternative settings on cached data without monkeypatching globals.
"""

from __future__ import annotations

from dataclasses import dataclass

_MIB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class IngestConfig:
    """Limits on what GhostCite accepts as input."""

    max_input_bytes: int = 10 * _MIB
    """Real papers and .bib files are well under 10 MiB; anything larger is almost always a
    scanned or image-heavy PDF that would be slow to process and yield no extractable text."""

    max_pdf_pages: int = 400
    """Long enough for a PhD thesis plus appendices, small enough to bound processing time."""

    min_text_chars_per_page: int = 20
    """Below this average, the PDF is treated as scanned (image-only). A real text page
    has hundreds of characters; scanned pages yield none or a stray page number."""

    max_references: int = 1000
    """A hard ceiling that protects memory and credits. Even large surveys rarely exceed
    this many references."""


@dataclass(frozen=True, slots=True)
class ParseConfig:
    """Heuristics for extracting fields from free-text references."""

    min_year: int = 1800
    """Older works are rarely cited in the papers GhostCite targets. Smaller four-digit
    numbers in a reference are far more often page numbers or volumes."""

    year_future_slack: int = 1
    """Accept next year's date because "in press" and early-access articles carry it."""

    min_title_chars: int = 10
    """Minimum number of letters in a title. A shorter "title" is almost always a parsing
    fragment, and searching it would waste a credit on noise. Real short titles such as
    "Deep learning" (12 letters) still pass."""


@dataclass(frozen=True, slots=True)
class SearchConfig:
    """How GhostCite talks to SerpApi."""

    default_max_searches: int = 50
    """A safe default for the 250-searches-per-month free plan: one typical paper fits,
    while a runaway input cannot drain the whole monthly quota."""

    timeout_seconds: float = 75.0
    """Most searches return in 1-15 s, but SerpApi retries proxies internally and can take
    much longer. A client-side timeout does not stop SerpApi from finishing (and billing)
    the search, so the timeout is generous: giving up early can cost an extra credit."""

    timeout_retry_delay_seconds: float = 15.0
    """Minimum wait before retrying after a timeout. If SerpApi was still working on the
    first request, this gives it time to finish, so the identical retry is answered free
    from SerpApi's one-hour cache instead of starting (and billing) a second search."""

    cache_detection_margin_seconds: float = 10.0
    """A retry counts as served from SerpApi's cache when the response's
    ``search_metadata.created_at`` is at least this much older than the moment the
    retry was sent. A cached response keeps the original search's metadata, which is
    at least ``timeout_retry_delay_seconds`` old. The margin is smaller than that delay,
    which leaves room for a few seconds of clock drift."""

    max_retries: int = 3
    """Enough to ride out a transient 5xx or network blip. More retries would mostly
    delay a clear error message for a real outage."""

    backoff_base_seconds: float = 1.0
    backoff_cap_seconds: float = 20.0
    """Exponential backoff with full jitter: 1 s, 2 s, 4 s … capped at 20 s, so retries
    from concurrent workers do not arrive in lockstep."""

    concurrency: int = 4
    """Bounded parallelism. It speeds up long lists roughly 4x while staying far below
    SerpApi's per-hour throughput limits on every plan."""

    results_per_query: int = 10
    """Scholar's default page size. Every page costs one credit regardless of size, so
    taking the full page gives the matcher the most candidates for free."""

    cache_ttl_days: int = 30
    """Scholar metadata for published papers is stable over weeks. Re-checking the same
    document within a month should cost nothing."""

    expected_searches_per_reference: float = 1.5
    """Planner average used for the preflight credit estimate. Most real references
    resolve with the first query; fabricated ones use two or three."""

    rate_limit_safety_fraction: float = 0.8
    """Pace live calls to at most 80% of the account's hourly limit. This leaves room
    for other clients of the same key and avoids relying on 429 retries."""

    language: str = "en"
    """Interface language (``hl``). Fixing it keeps cache keys and result formats stable
    across machines with different locales."""

    google_country: str = "in"
    """Country (``gl``) for Google web fallback searches. Without it SerpApi picks a proxy
    location per request, and results (even their language) vary between runs. India
    is chosen because the fallback exists mainly for Indian books and theses."""

    max_query_chars: int = 256
    """Google ignores words beyond about 32. Long titles are cut at a word boundary, which
    also keeps cache keys short."""

    fallback_entry_types: frozenset[str] = frozenset(
        {"book", "inbook", "incollection", "phdthesis", "mastersthesis", "thesis", "techreport",
         "report", "manual", "booklet"}
    )  # fmt: skip
    """Work types that Google Scholar indexes poorly, which get a third, plain Google web
    search. Journal and conference papers never use it, so fabricated papers cost at
    most two credits."""


@dataclass(frozen=True, slots=True)
class MatchConfig:
    """Scoring of a candidate against a citation."""

    title_match: float = 0.90
    """At or above this normalized similarity, two titles name the same work. Case,
    punctuation, subtitle-separator and small typo variants of one title score above
    0.9, while distinct papers that share many words score well below it."""

    title_reject: float = 0.70
    """Below this, the candidate is a different work. Between the two thresholds the
    match is ambiguous, so the planner tries the next query strategy."""

    subtitle_match_score: float = 0.90
    """Score given when one title is exactly the other's main title (a dropped subtitle).
    It equals ``title_match``: the same work, cited in a common shortened form."""

    surname_match: float = 0.85
    """Fuzzy threshold for surnames, so transliteration variants ("Muller"/"Mueller",
    "Chowdhury"/"Choudhury") still count as the same author."""

    partial_year_score: float = 0.8
    """Score for a year that is off by no more than ``year_tolerance``: probably the
    preprint and the published version, so it is not counted as fully equal."""

    year_tolerance: int = 1
    """Preprints and conference versions often appear a year before the journal version,
    so a difference of one year is not treated as a citation error."""

    author_overlap_match: float = 0.5
    """Share of comparable cited surnames found among the candidate's authors. Scholar
    truncates long author lists, so requiring every author would penalize correct
    citations of large collaborations."""

    venue_match: float = 0.70
    """Venue strings differ wildly in abbreviation ("Proc. NeurIPS" vs "Advances in
    Neural Information Processing Systems"), so only clear disagreement counts."""

    weight_title: float = 0.55
    weight_authors: float = 0.20
    weight_year: float = 0.15
    weight_venue: float = 0.10
    """The title dominates because it is the most specific identifier a citation has.
    Authors and year confirm identity. The venue is the noisiest field and gets the least
    weight. The weights sum to 1, so the combined confidence stays in [0, 1]."""

    doi_match_confidence: float = 0.98
    """An exact DOI match identifies the work almost unambiguously."""

    fallback_confidence_cap: float = 0.70
    """Google web results carry no structured authors or venue, so a match found only
    there can never be as certain as a Scholar match."""


@dataclass(frozen=True, slots=True)
class VerdictConfig:
    """How confident each verdict is allowed to be."""

    not_found_confidence: float = 0.9
    """NOT_FOUND when no search returned anything resembling the title. It is not 1.0,
    because Scholar has coverage gaps (regional journals, very new papers)."""

    not_found_floor: float = 0.5
    """Lowest NOT_FOUND confidence. The closer the best title, the less sure the verdict:
    confidence = max(floor, not_found_confidence - best_title_similarity / 2)."""

    ambiguous_title_mismatch_authors: float = 1.0
    """A title in the ambiguous band only counts as a garbled citation of a real paper
    (METADATA_MISMATCH) when every comparable author matches and the year agrees.
    Otherwise it is NOT_FOUND."""


@dataclass(frozen=True, slots=True)
class ScoreConfig:
    """Document-level integrity score."""

    mismatch_weight: float = 0.5
    """A real paper cited with wrong details is a lesser error than a fabricated one, so it
    counts half: integrity = 100 * (verified + 0.5 * mismatched) / checked."""


@dataclass(frozen=True, slots=True)
class WebConfig:
    """Safety limits for the local web UI."""

    default_host: str = "127.0.0.1"
    """Loopback by default, so nothing on the network can spend the user's credits."""

    default_port: int = 8000
    max_upload_bytes: int = 10 * _MIB
    """Same reasoning as ``IngestConfig.max_input_bytes``."""

    per_job_search_cap: int = 30
    """One web check can never spend more than 30 credits."""

    global_search_budget: int = 100
    """Total live searches one server process may spend across all jobs."""

    max_concurrent_jobs: int = 2
    """Bounds CPU, memory and parallel SerpApi load on a laptop."""

    max_references_per_job: int = 300
    """Larger lists belong in the CLI, where the budget is explicit."""

    job_ttl_seconds: int = 900
    """Results stay in memory for 15 minutes so downloads work, then they are discarded."""


INGEST = IngestConfig()
PARSE = ParseConfig()
SEARCH = SearchConfig()
MATCH = MatchConfig()
VERDICT = VerdictConfig()
SCORE = ScoreConfig()
WEB = WebConfig()
