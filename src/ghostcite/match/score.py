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
_MIN_JOINED_PART_CHARS = 3
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


def _dropped_subtitle(cited: str, found: str) -> bool:
    """One title is exactly the other's main title ("Wings of Fire" / "...: An Autobiography")."""
    a, b = fold(cited), fold(found)
    main_a, main_b = fold(main_title(cited)), fold(main_title(found))
    dropped = (main_a == b and main_a != a) or (main_b == a and main_b != b)
    return dropped and len(min(main_a, main_b, key=len).split()) >= _MIN_SUBTITLE_MAIN_WORDS


def title_similarity(cited: str, found: str, cfg: MatchConfig = MATCH) -> float:
    """Character-level similarity of two titles in [0, 1], robust to case, punctuation and order.

    A dropped subtitle raises the score to ``cfg.subtitle_match_score``.
    """
    a, b = fold(cited), fold(found)
    if not a or not b:
        return 0.0
    score = max(fuzz.ratio(a, b), fuzz.token_sort_ratio(a, b)) / 100
    if _dropped_subtitle(cited, found):
        score = max(score, cfg.subtitle_match_score)
    return round(score, 4)


def _covered(words: Sequence[str], others: Sequence[str], cfg: MatchConfig) -> bool:
    """Every word has a counterpart: equal, a close spelling, or part of a joined word."""
    joined = "".join(others)
    for word in words:
        if any(
            word == other or fuzz.ratio(word, other) / 100 >= cfg.title_word_match
            for other in others
        ):
            continue
        if len(word) >= _MIN_JOINED_PART_CHARS and word in joined:
            continue  # "pre training" against "pretraining"
        return False
    return True


def same_words(cited: str, found: str, cfg: MatchConfig = MATCH) -> bool:
    """True when both titles use the same significant words, allowing typos.

    Character similarity alone cannot tell a typo ("recognitoin") from a swapped word
    ("Attention is all *we* need"). A reworded title is a classic hallucination
    signature, so a title only matches when no significant word is replaced, added
    or missing.
    """
    a, b = tokens(cited, drop_stopwords=True), tokens(found, drop_stopwords=True)
    return bool(a) and bool(b) and _covered(a, b, cfg) and _covered(b, a, cfg)


def is_title_match(cited: str, found: str, cfg: MatchConfig = MATCH) -> bool:
    """The same title: very similar characters and the same words, or a dropped subtitle."""
    if _dropped_subtitle(cited, found):
        return True
    return title_similarity(cited, found, cfg) >= cfg.title_match and same_words(cited, found, cfg)


def title_overlap(cited: str, found: str, cfg: MatchConfig = MATCH) -> float:
    """How much of one title appears in the other, in [0, 1].

    It is the larger of the full similarity and the best alignment of the shorter title
    inside the longer one. That catches embellished or reworded versions of a real
    title ("Attention is all we need for sequence transduction"), which define the middle
    band. Short titles (fewer than ``cfg.overlap_min_words`` words) use full similarity
    only, because a two-word title appears inside many unrelated titles.
    """
    a, b = fold(cited), fold(found)
    if not a or not b:
        return 0.0
    similarity = title_similarity(cited, found, cfg)
    if min(len(a.split()), len(b.split())) < cfg.overlap_min_words:
        return similarity
    return round(max(similarity, fuzz.partial_ratio(a, b) / 100), 4)


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
    """Compare every field of a citation with one candidate.

    The title is ``MATCH`` only for the same title, ``PARTIAL`` in the middle band (a
    reworded or embellished version of it), and ``MISMATCH`` otherwise.
    """
    cited_title = fields.title or ""
    title = title_similarity(cited_title, candidate.title, cfg)
    if is_title_match(cited_title, candidate.title, cfg):
        title_status = FieldStatus.MATCH
    elif title_overlap(cited_title, candidate.title, cfg) >= cfg.title_reject:
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


def first_author_agrees(
    fields: ParsedFields, candidate: Candidate, cfg: MatchConfig = MATCH
) -> bool:
    """The cited first author is the candidate's first author (surname comparison)."""
    if not fields.authors or not candidate.authors:
        return False
    cited, found = surname_key(fields.authors[0].surname), surname_key(candidate.authors[0])
    return bool(cited) and bool(found) and _same_surname(cited, found, cfg)


def title_status(result: MatchResult) -> FieldStatus:
    """The title comparison status of ``result``."""
    field = result.field(FieldName.TITLE)
    return field.status if field is not None else FieldStatus.UNKNOWN


def _title_score(result: MatchResult) -> float:
    field = result.field(FieldName.TITLE)
    return field.score if field is not None and field.score is not None else 0.0


_JUDGED = (FieldName.AUTHORS, FieldName.YEAR, FieldName.VENUE)
_AGREEING = (FieldStatus.MATCH, FieldStatus.PARTIAL)


def agreement(result: MatchResult) -> tuple[int, int]:
    """(fields that disagree, fields that agree) among authors, year and venue."""
    statuses = [f.status for name in _JUDGED if (f := result.field(name)) is not None]
    return (
        sum(status is FieldStatus.MISMATCH for status in statuses),
        sum(status in _AGREEING for status in statuses),
    )


def in_middle_band(result: MatchResult, fields: ParsedFields, cfg: MatchConfig = MATCH) -> bool:
    """A reworded title whose first author and year (within tolerance) agree."""
    year = result.field(FieldName.YEAR)
    return (
        title_status(result) is FieldStatus.PARTIAL
        and first_author_agrees(fields, result.candidate, cfg)
        and year is not None
        and year.status in _AGREEING
    )


def best_match(
    results: Sequence[MatchResult], fields: ParsedFields, cfg: MatchConfig = MATCH
) -> MatchResult | None:
    """Pick the candidate that most likely is the cited work, from every result on the page.

    A work often appears as several results (preprint, conference and journal versions).
    Among title-matching candidates, the one that agrees on the most fields wins (fewest
    disagreements, then most agreements, then confidence and citation count). So a
    citation of the journal version is verified even when Scholar ranks the conference
    version first. Without a title match, middle-band candidates whose first author and
    year agree are preferred, then the closest title.
    """
    if not results:
        return None
    matching = [r for r in results if title_status(r) is FieldStatus.MATCH]
    if matching:

        def rank(result: MatchResult) -> tuple[int, int, float, int]:
            disagree, agree = agreement(result)
            return (-disagree, agree, result.confidence, result.candidate.cited_by or 0)

        return max(matching, key=rank)
    return max(
        results,
        key=lambda r: (in_middle_band(r, fields, cfg), _title_score(r), r.confidence),
    )


def versions_of(results: Sequence[MatchResult]) -> int | None:
    """Most versions Scholar reports for any title-matching candidate (all are the same work)."""
    counts = [
        r.candidate.versions
        for r in results
        if title_status(r) is FieldStatus.MATCH and r.candidate.versions is not None
    ]
    return max(counts) if counts else None
