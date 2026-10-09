"""Extract structured fields from one free-text reference.

Citation styles disagree on almost everything, but three anchors are reliable enough to
build on. Strategies are tried from most to least reliable, and each carries the
confidence it earned:

1. **Quoted title** (IEEE, MLA): ``A. Vaswani, "Attention is all you need," NeurIPS``.
2. **Year after authors** (APA, Harvard, ACM): ``Vaswani, A. (2017). Attention …``.
3. **Title after the author list** (Vancouver, Springer, plain): the longest prefix
   that still parses as a list of names is the author list; the next sentence is the
   title.

Whatever follows the title, up to the first volume, page or year number, is the venue.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ghostcite.config import PARSE, ParseConfig
from ghostcite.models import ParseConfidence, ParsedFields
from ghostcite.parse.names import AuthorList, parse_authors

_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>{}]+)", re.IGNORECASE)
_DOI_PREFIX = re.compile(r"(?:https?://(?:dx\.)?doi\.org/|\bdoi\s*:\s*)", re.IGNORECASE)
_URL = re.compile(r"(?:https?://|\bwww\.)\S+", re.IGNORECASE)
_URL_NOISE = re.compile(
    r"\[(?:online)\]|\b(?:available\s*(?:at|from)?|accessed|retrieved)\b[^.]*:?", re.I
)
_ARXIV = re.compile(r"\barxiv(?:\s+preprint)?\s*:?\s*(?:arxiv:)?\s*\d{4}\.\d{4,5}(?:v\d+)?", re.I)
# A plausible publication year that is not part of a page range or a longer number.
_YEAR = re.compile(r"(?<![\d\u2013-])((?:1[89]|20)\d{2})([a-z])?(?!\d)(?!\s*[\u2013-]\s*\d)")
_QUOTED = re.compile(
    r"[\u201c\"\u00ab]\s*(?P<title>[^\u201d\"\u00bb]+?)\s*[,.]?\s*[\u201d\"\u00bb]"
)
_BOUNDARY = re.compile(r"[.?!](?=\s+\S|\s*$)")
_AUTHOR_BREAK = re.compile(r"(?<=\S)[.:](?=\s+\S)")
_VENUE_LEAD = re.compile(r"^(?:in\s*:|in\b)\s*", re.IGNORECASE)
_VENUE_END = re.compile(
    r"(?:[,.;:]?\s*)(?:\(|\b(?:vol|volume|no|issue|pp|pages|chapter|ch)\b\.?|\d)", re.IGNORECASE
)
# Abbreviations that end with a period without ending a sentence.
_ABBREVIATIONS = frozenset(
    {
        *("al", "vol", "no", "nos", "pp", "eds", "ed", "proc", "int", "j", "conf", "dept"),
        *("univ", "trans", "rev", "symp", "vs", "fig", "eq", "st", "jr", "sr"),
    }
)
_BOOK_HINTS = re.compile(
    r"\b(?:press|publishers?|publishing|edition|ed\.|isbn|verlag|books?|springer\s+nature)\b",
    re.IGNORECASE,
)
_THESIS_HINTS = re.compile(r"\b(?:thesis|dissertation|ph\.?\s?d\.?|m\.?\s?tech|master'?s)\b", re.I)
_REPORT_HINTS = re.compile(
    r"\b(?:technical\s+report|tech\.\s*rep\.?|working\s+paper|white\s+paper)\b", re.I
)

_MIN_VENUE_CHARS = 3
# A list marker left on the reference ("[1] ", "(1) ", "1. ") would be read as an author.
_LEADING_MARKER = re.compile(r"^\s*(?:\[\d{1,4}\]|\(\d{1,4}\)|\d{1,4}\.(?=\s))\s*")
_MAX_AUTHOR_PREFIX_CHARS = 600


@dataclass(frozen=True, slots=True)
class _Title:
    text: str
    start: int
    end: int
    authors_end: int
    """Index where the author segment ends (exclusive)."""
    confidence: float


@dataclass(frozen=True, slots=True)
class _Year:
    value: int
    start: int
    end: int
    confidence: float


def find_doi(text: str) -> str | None:
    """Return the first DOI in ``text``, lowercased, without trailing punctuation."""
    match = _DOI.search(text)
    if match is None:
        return None
    return match.group(1).rstrip(".,;:)]}'\u201d").lower()


def _strip_noise(text: str) -> str:
    """Remove DOIs, URLs and access notes, which contain numbers that look like years."""
    text = _DOI.sub(" ", _DOI_PREFIX.sub(" ", text))
    text = _URL_NOISE.sub(" ", _URL.sub(" ", text))
    return re.sub(r"\s+", " ", text).strip(" ,;")


def find_year(
    text: str, cfg: ParseConfig = PARSE, *, current_year: int | None = None
) -> _Year | None:
    """Pick the publication year.

    A year in parentheses ("(2019)", "(2019a)") is the strongest signal. Otherwise a year
    that directly follows the author list ("Vaswani, A. 2017.") wins, then the last
    year in the reference (IEEE puts it at the end).
    """
    latest = (current_year or datetime.now(tz=UTC).year) + cfg.year_future_slack
    found = [m for m in _YEAR.finditer(text) if cfg.min_year <= int(m.group(1)) <= latest]
    if not found:
        return None
    for m in found:
        if m.start() > 0 and text[m.start() - 1] == "(":
            return _Year(int(m.group(1)), m.start(), m.end(), 0.95)
    distinct = {m.group(1) for m in found}
    confidence = 0.85 if len(distinct) == 1 else 0.6
    for m in found:
        if text[m.end() : m.end() + 1] == "." and _looks_like_authors(text[: m.start()]):
            return _Year(int(m.group(1)), m.start(), m.end(), confidence)
    last = found[-1]
    return _Year(int(last.group(1)), last.start(), last.end(), confidence)


def _looks_like_authors(segment: str) -> bool:
    """True when every part of ``segment`` parses as a person's name."""
    authors = parse_authors(segment.strip(" .,;:("))
    return bool(authors.authors) and authors.confidence == 1.0


def _sentence_end(text: str, start: int) -> int:
    """Index where the sentence starting at ``start`` ends, skipping initials and abbreviations."""
    for match in _BOUNDARY.finditer(text, start):
        before = text[start : match.start()].split()
        word = before[-1].lower() if before else ""
        if match.group() == "." and (word in _ABBREVIATIONS or re.fullmatch(r"[a-z]", word)):
            continue
        return match.start() + (1 if match.group() in "?!" else 0)
    return len(text)


def _is_plausible_title(title: str, cfg: ParseConfig) -> bool:
    """Long enough to be a real title, counting letters only (years and quotes do not count)."""
    return sum(ch.isalpha() for ch in title) >= cfg.min_title_chars


def _quoted_title(text: str, cfg: ParseConfig) -> _Title | None:
    for match in _QUOTED.finditer(text):
        title = match.group("title").strip()
        if _is_plausible_title(title, cfg):
            return _Title(title, match.start("title"), match.end(), match.start(), 0.95)
    return None


def _title_after_year(text: str, year: _Year | None) -> _Title | None:
    if year is None:
        return None
    lead = text[: year.start].rstrip(" (")
    if not lead or not _looks_like_authors(lead):
        return None
    after = re.match(r"[a-z]?\)?[.,:]?\s+", text[year.end :])
    if after is None:
        return None
    start = year.end + after.end()
    end = _sentence_end(text, start)
    return _Title(text[start:end], start, end, len(lead), 0.85)


def _title_after_authors(text: str) -> _Title | None:
    """Take the longest prefix that is still a clean author list; the title follows it."""
    best: tuple[int, int] | None = None
    for match in _AUTHOR_BREAK.finditer(text):
        if match.start() > _MAX_AUTHOR_PREFIX_CHARS:
            break
        authors = parse_authors(text[: match.start()])
        if authors.authors and authors.confidence == 1.0:
            best = (match.start(), match.end())
        elif best is not None:
            break
    if best is None:
        return None
    start = best[1] + len(text[best[1] :]) - len(text[best[1] :].lstrip())
    end = _sentence_end(text, start)
    return _Title(text[start:end], start, end, best[0], 0.7)


def _first_sentence_title(text: str) -> _Title | None:
    """Last resort: no author list was recognized, so the first sentence may be the title.

    A sentence that is only a name list plus a year ("Smith J. 2010.") is not a title.
    """
    end = _sentence_end(text, 0)
    without_years = _YEAR.sub(" ", text[:end]).strip(" .,;:()")
    if not without_years or _looks_like_authors(without_years):
        return None
    return _Title(text[:end], 0, end, 0, 0.3)


def _find_title(text: str, year: _Year | None, cfg: ParseConfig) -> tuple[_Title, str] | None:
    """Try each title strategy in order of reliability; keep the first plausible result."""
    strategies: tuple[Callable[[], _Title | None], ...] = (
        lambda: _quoted_title(text, cfg),
        lambda: _title_after_year(text, year),
        lambda: _title_after_authors(text),
        lambda: _first_sentence_title(text),
    )
    for strategy in strategies:
        candidate = strategy()
        if candidate is not None:
            cleaned = _clean_title(candidate.text)
            if _is_plausible_title(cleaned, cfg):
                return candidate, cleaned
    return None


def _clean_title(title: str) -> str:
    title = title.strip().strip("\u201c\u201d\"'\u00ab\u00bb").strip()
    return title.rstrip(".,;: ").strip()


def find_venue(after_title: str) -> str | None:
    """Venue name: the text after the title, up to the first volume, page or year number."""
    text = after_title.lstrip(' .,;:\u201d"')
    if _ARXIV.search(text):
        return "arXiv"
    text = _VENUE_LEAD.sub("", text)
    end = _VENUE_END.search(text)
    venue = (text[: end.start()] if end else text).strip(" .,;:()")
    return venue if len(venue) >= _MIN_VENUE_CHARS else None


def guess_entry_type(text: str) -> str | None:
    """Guess a BibTeX-like type for works Google Scholar indexes poorly (books, theses, reports)."""
    if _THESIS_HINTS.search(text):
        return "phdthesis"
    if _REPORT_HINTS.search(text):
        return "techreport"
    if _BOOK_HINTS.search(text):
        return "book"
    return None


def parse_fields(
    raw: str, cfg: ParseConfig = PARSE, *, current_year: int | None = None
) -> ParsedFields:
    """Extract title, authors, year, venue and DOI from one reference string."""
    doi = find_doi(raw)
    text = _strip_noise(_LEADING_MARKER.sub("", raw))
    if not text:
        return ParsedFields(doi=doi, confidence=ParseConfidence(doi=1.0 if doi else 0.0))

    year = find_year(text, cfg, current_year=current_year)
    found = _find_title(text, year, cfg)
    if found is not None:
        title, title_text = found
        authors_end = title.authors_end
        if year is not None and authors_end > year.start:
            authors_end = year.start
        venue = find_venue(text[title.end :])
    else:
        title, title_text, venue = None, None, None
        authors_end = year.start if year is not None else len(text)
    segment = text[:authors_end].strip(" .,;:(")
    authors = parse_authors(segment) if segment else AuthorList((), False, 0.0)

    return ParsedFields(
        title=title_text,
        authors=authors.authors,
        et_al=authors.et_al,
        year=year.value if year else None,
        venue=venue,
        doi=doi,
        entry_type=guess_entry_type(raw),
        confidence=ParseConfidence(
            title=title.confidence if title is not None else 0.0,
            authors=round(authors.confidence * 0.9, 3) if authors.authors else 0.0,
            year=year.confidence if year else 0.0,
            venue=0.6 if venue else 0.0,
            doi=1.0 if doi else 0.0,
        ),
    )
