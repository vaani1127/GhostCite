"""Score how well a search candidate matches a citation, field by field.

Every field comparison yields a :class:`FieldMatch` with a status:

* ``MATCH`` / ``PARTIAL``: agreement (``PARTIAL`` covers tolerated differences such as
  a preprint published one year later).
* ``MISMATCH``: clear disagreement. Only this status can make a verdict
  METADATA_MISMATCH.
* ``UNKNOWN``: a side is missing the field, or it cannot be judged fairly (truncated
  author lists, a venue acronym against its full name). Unknown fields are left out of
  the combined confidence instead of counting as errors.
"""

from __future__ import annotations

from collections.abc import Sequence

from rapidfuzz import fuzz

from ghostcite.config import MATCH, MatchConfig
from ghostcite.match.normalize import fold, main_title, surname_key, tokens
from ghostcite.models import (
    Author,
    Candidate,
    Engine,
    FieldMatch,
    FieldName,
    FieldStatus,
    MatchResult,
    ParsedFields,
)

_MIN_SUBTITLE_MAIN_WORDS = 2
_MIN_ABBREVIATION_CHARS = 3
# Words that say what kind of venue it is, not which one.
_GENERIC_VENUE_WORDS = frozenset(
    {
        *("proceedings", "proc", "conference", "conf", "journal", "j", "international"),
        *("int", "annual", "workshop", "symposium", "transactions", "trans", "ieee"),
        *("acm", "vol", "volume", "edition", "eds", "ed", "press", "series"),
    }
)
_MIN_VENUE_TOKENS = 2


def title_similarity(cited: str, found: str, cfg: MatchConfig = MATCH) -> float:
    """Similarity of two titles in [0, 1], robust to case, punctuation and word order.

    When one title is exactly the other's main title (a dropped subtitle, as in
    "Wings of Fire" against "Wings of Fire: An Autobiography"), the score is raised to
    ``cfg.subtitle_match_score``.
    """
    a, b = fold(cited), fold(found)
    if not a or not b:
        return 0.0
    score = max(fuzz.ratio(a, b), fuzz.token_sort_ratio(a, b)) / 100
    main_a, main_b = fold(main_title(cited)), fold(main_title(found))
    dropped_subtitle = (main_a == b and main_a != a) or (main_b == a and main_b != b)
    if dropped_subtitle and len(min(main_a, main_b, key=len).split()) >= _MIN_SUBTITLE_MAIN_WORDS:
        score = max(score, cfg.subtitle_match_score)
    return round(score, 4)


def _same_surname(a: str, b: str, cfg: MatchConfig) -> bool:
    """Equal, or close enough for transliteration variants ("muller" / "mueller")."""
    return a == b or (min(len(a), len(b)) >= 4 and fuzz.ratio(a, b) / 100 >= cfg.surname_match)


def compare_authors(
    cited: Sequence[Author], found: Sequence[str], found_truncated: bool, cfg: MatchConfig = MATCH
) -> FieldMatch:
    """Share of cited surnames present among the candidate's authors.

    Scholar shows only the first few authors of long lists. When the candidate's list is
    truncated, only as many cited authors as were shown are compared.
    """
    cited_keys = [k for k in (surname_key(a.surname) for a in cited) if k]
    found_keys = [k for k in (surname_key(name) for name in found) if k]
    cited_text = ", ".join(a.surname for a in cited) or None
    found_text = ", ".join(found) or None
    if not cited_keys or not found_keys:
        return FieldMatch(
            field=FieldName.AUTHORS, status=FieldStatus.UNKNOWN, cited=cited_text, found=found_text
        )
    comparable = cited_keys[: len(found_keys)] if found_truncated else cited_keys
    hits = sum(1 for key in comparable if any(_same_surname(key, f, cfg) for f in found_keys))
    share = hits / len(comparable)
    if share >= 1.0:
        status = FieldStatus.MATCH
    elif share >= cfg.author_overlap_match:
        status = FieldStatus.PARTIAL
    else:
        status = FieldStatus.MISMATCH
    return FieldMatch(
        field=FieldName.AUTHORS,
        status=status,
        score=round(share, 4),
        cited=cited_text,
        found=found_text,
    )


def compare_year(cited: int | None, found: int | None, cfg: MatchConfig = MATCH) -> FieldMatch:
    """Equal years match; a difference within ``year_tolerance`` is a partial match."""
    if cited is None or found is None:
        return FieldMatch(
            field=FieldName.YEAR,
            status=FieldStatus.UNKNOWN,
            cited=str(cited) if cited else None,
            found=str(found) if found else None,
        )
    delta = abs(cited - found)
    if delta == 0:
        status, score = FieldStatus.MATCH, 1.0
    elif delta <= cfg.year_tolerance:
        status, score = FieldStatus.PARTIAL, cfg.partial_year_score
    else:
        status, score = FieldStatus.MISMATCH, 0.0
    return FieldMatch(
        field=FieldName.YEAR, status=status, score=score, cited=str(cited), found=str(found)
    )


def _venue_tokens(venue: str) -> list[str]:
    return [t for t in tokens(venue, drop_stopwords=True) if t not in _GENERIC_VENUE_WORDS]


def _abbreviation_overlap(short: list[str], long: list[str]) -> float:
    """Share of ``short`` tokens that match ``long`` tokens in order.

    Abbreviations count as matches: "adv neural inf process syst" against
    "advances in neural information processing systems" scores 1.0.
    """
    position = matched = 0
    for token in short:
        for index in range(position, len(long)):
            word = long[index]
            if token == word or (
                len(token) >= _MIN_ABBREVIATION_CHARS
                and (word.startswith(token) or token.startswith(word))
            ):
                matched += 1
                position = index + 1
                break
    return matched / len(short) if short else 0.0


def venue_similarity(cited: str, found: str) -> float:
    """Similarity of venue names, tolerant of abbreviations and Scholar's truncation."""
    a, b = _venue_tokens(cited), _venue_tokens(found)
    if not a or not b:
        return 0.0
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    fuzzy = fuzz.token_set_ratio(" ".join(a), " ".join(b)) / 100
    return round(max(fuzzy, _abbreviation_overlap(short, long)), 4)


def compare_venue(cited: str | None, found: str | None, cfg: MatchConfig = MATCH) -> FieldMatch:
    """Venue agreement. Acronyms and one-word venues are only judged when they are equal."""
    if not cited or not found:
        return FieldMatch(
            field=FieldName.VENUE, status=FieldStatus.UNKNOWN, cited=cited, found=found
        )
    score = venue_similarity(cited, found)
    judgeable = min(len(_venue_tokens(cited)), len(_venue_tokens(found))) >= _MIN_VENUE_TOKENS
    if score >= cfg.venue_match:
        status = FieldStatus.MATCH
    elif judgeable:
        status = FieldStatus.MISMATCH
    else:
        status = FieldStatus.UNKNOWN  # "NeurIPS" vs "Advances in neural ...": cannot judge
    return FieldMatch(field=FieldName.VENUE, status=status, score=score, cited=cited, found=found)


def compare_doi(cited: str | None, candidate: Candidate) -> FieldMatch:
    """A cited DOI that appears in the candidate's link identifies the work exactly."""
    if not cited or not candidate.link:
        return FieldMatch(field=FieldName.DOI, status=FieldStatus.UNKNOWN, cited=cited)
    found = cited.lower() in candidate.link.lower()
    return FieldMatch(
        field=FieldName.DOI,
        status=FieldStatus.MATCH if found else FieldStatus.UNKNOWN,
        score=1.0 if found else None,
        cited=cited,
        found=cited if found else None,
    )


def _weight(name: FieldName, cfg: MatchConfig) -> float:
    return {
        FieldName.TITLE: cfg.weight_title,
        FieldName.AUTHORS: cfg.weight_authors,
        FieldName.YEAR: cfg.weight_year,
        FieldName.VENUE: cfg.weight_venue,
    }.get(name, 0.0)


def combine(fields: Sequence[FieldMatch], engine: Engine, cfg: MatchConfig = MATCH) -> float:
    """Weighted mean of the judged fields' scores, with DOI and fallback adjustments.

    Unknown fields are excluded and the remaining weights renormalized, so a citation is
    not penalized for information it never gave.
    """
    judged = [f for f in fields if f.status is not FieldStatus.UNKNOWN and f.score is not None]
    weights = [_weight(f.field, cfg) for f in judged]
    total = sum(weights)
    confidence = (
        sum(w * (f.score or 0.0) for w, f in zip(weights, judged, strict=True)) / total
        if total
        else 0.0
    )
    if any(f.field is FieldName.DOI and f.status is FieldStatus.MATCH for f in fields):
        confidence = max(confidence, cfg.doi_match_confidence)
    if engine is Engine.GOOGLE:
        confidence = min(confidence, cfg.fallback_confidence_cap)
    return round(min(1.0, max(0.0, confidence)), 4)


def match_candidate(
    fields: ParsedFields, candidate: Candidate, cfg: MatchConfig = MATCH
) -> MatchResult:
    """Compare every field of a citation with one candidate."""
    title = title_similarity(fields.title or "", candidate.title, cfg)
    if title >= cfg.title_match:
        title_status = FieldStatus.MATCH
    elif title >= cfg.title_reject:
        title_status = FieldStatus.PARTIAL
    else:
        title_status = FieldStatus.MISMATCH
    comparisons = (
        FieldMatch(
            field=FieldName.TITLE,
            status=title_status,
            score=title,
            cited=fields.title,
            found=candidate.title,
        ),
        compare_authors(fields.authors, candidate.authors, candidate.authors_truncated, cfg),
        compare_year(fields.year, candidate.year, cfg),
        compare_venue(fields.venue, candidate.venue, cfg),
        compare_doi(fields.doi, candidate),
    )
    return MatchResult(
        candidate=candidate,
        fields=comparisons,
        confidence=combine(comparisons, candidate.engine, cfg),
    )


def best_match(results: Sequence[MatchResult], cfg: MatchConfig = MATCH) -> MatchResult | None:
    """Pick the candidate that most likely is the cited work.

    Among candidates whose title matches, the most confident wins, which separates
    the original paper from, e.g., "study notes" with the same title. Without any title
    match, the closest title wins.
    """
    if not results:
        return None

    def title_score(result: MatchResult) -> float:
        field = result.field(FieldName.TITLE)
        return field.score if field is not None and field.score is not None else 0.0

    matching = [r for r in results if title_score(r) >= cfg.title_match]
    if matching:
        return max(
            matching, key=lambda r: (r.confidence, title_score(r), r.candidate.cited_by or 0)
        )
    return max(results, key=lambda r: (title_score(r), r.confidence))
