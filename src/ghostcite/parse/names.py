"""Parse author lists in the many formats real reference lists use.

Supported shapes, all of which can be mixed with ``and``, ``&`` and ``et al.``:

* ``Vaswani, A., Shazeer, N.``      (APA: surname, initials)
* ``Vaswani A, Shazeer N``          (Vancouver: surname initials)
* ``A. Vaswani, N. Shazeer``        (IEEE: initials surname)
* ``Ashish Vaswani, Noam Shazeer``  (full names)
* ``A. P. J. Abdul Kalam``, ``Sharma AK``, ``R. K. Narayan`` (Indian initials styles)
* ``Jean de la Fontaine``           (lowercase particles stay with the surname)

Only the surname is used for matching. Google Scholar shows authors as "initials
surname", and the surname is the part that survives every citation style.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ghostcite.models import Author

_ET_AL = re.compile(r"(?:,\s*)?\b(?:et\.?\s*al(?:ii|ia)?\b\.?|and\s+others\b)", re.IGNORECASE)
_SEPARATOR = re.compile(r"\s*(?:,\s*)?(?:\band\b|&)\s*", re.IGNORECASE)
# "A.", "A", "A.K.", "AK", "J.-P.", "J-P": one to four initials, with or without periods.
_INITIALS = re.compile(r"^(?:[A-Z]\.?(?:-[A-Z]\.?)?){1,4}$")
# A capitalized word made of letters, apostrophes, hyphens and an optional final period:
# "O'Brien", "Müller-Lüdenscheidt", "D'Souza". Colons, digits and brackets never occur.
_NAME_WORD = re.compile(r"^[^\W\d_]+(?:['\u2019-][^\W\d_]+)*\.?$")
_SUFFIXES = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"})
_PARTICLES = frozenset(
    {
        *("van", "von", "der", "den", "de", "del", "della", "di", "da", "du", "dos", "das"),
        *("la", "le", "bin", "binti", "ibn", "al", "el", "ter", "ten", "st.", "zu"),
    }
)
_MAX_NAME_WORDS = 5


@dataclass(frozen=True, slots=True)
class AuthorList:
    """Result of parsing an author segment."""

    authors: tuple[Author, ...]
    et_al: bool
    confidence: float
    """Share of comma/and-separated parts that looked like a person's name, in [0, 1]."""


def is_initials(word: str) -> bool:
    """True for initials-only tokens such as ``A.``, ``AK``, ``A.K.`` or ``J.-P.``."""
    return bool(_INITIALS.match(word))


def _is_name_word(word: str, *, last: bool) -> bool:
    if word.lower() in _PARTICLES or is_initials(word):
        return True
    # A full word ending in a period inside a name means we ran into the next sentence
    # ("G. Hinton. Deep Learning").
    if word.endswith(".") and not last:
        return False
    return word[0].isupper() and bool(_NAME_WORD.match(word))


def _split_name(words: list[str]) -> Author | None:
    """Assign surname and given names, given that every word is a plausible name word."""
    flags = [is_initials(w) for w in words]
    if all(flags):
        return None
    leading = next(i for i, flag in enumerate(flags) if not flag)
    trailing = next(i for i, flag in enumerate(reversed(flags)) if not flag)
    middle = sum(flags) - leading - trailing
    if leading and not middle:  # "A. K. Sharma", "A. P. J. Abdul Kalam"
        return Author(surname=" ".join(words[leading:]), given=" ".join(words[:leading]))
    if trailing and not middle:  # "Sharma AK", "Vaswani A"
        return Author(surname=" ".join(words[:-trailing]), given=" ".join(words[-trailing:]))
    if leading or trailing:
        return None
    if middle:
        # Only "Given I. [I.] Surname" is a name; initials elsewhere mean a title crept in.
        first, last = flags.index(True), len(flags) - 1 - flags[::-1].index(True)
        if first != 1 or last != len(words) - 2:
            return None
    surname_start = len(words) - 1
    while surname_start > 1 and words[surname_start - 1].lower() in _PARTICLES:
        surname_start -= 1
    return Author(surname=" ".join(words[surname_start:]), given=" ".join(words[:surname_start]))


def parse_name(text: str) -> Author | None:
    """Parse one person's name, or return ``None`` if it does not look like one."""
    words = [w for w in text.replace(",", " ").split() if w.lower() not in _SUFFIXES]
    if not words or len(words) > _MAX_NAME_WORDS:
        return None
    if not all(_is_name_word(w, last=i == len(words) - 1) for i, w in enumerate(words)):
        return None
    if all(w.lower() in _PARTICLES for w in words):
        return None
    if len(words) == 1:
        word = words[0].rstrip(".")
        return None if is_initials(words[0]) and len(word) <= 2 else Author(surname=word)
    return _split_name(words)


def _clean_token(token: str) -> str:
    token = token.strip()
    return token if is_initials(token) else token.strip(" .;:")


def _pair_surname_initials(tokens: list[str]) -> list[str]:
    """Rejoin "Surname, I." pairs that splitting on commas tore apart."""
    all_single_words = len(tokens) % 2 == 0 and all(" " not in t for t in tokens)
    names: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        is_bare_surname = " " not in token and not is_initials(token)
        if nxt is not None and is_bare_surname:
            given_follows = all(is_initials(w) for w in nxt.split()) or all_single_words
            if given_follows:
                names.append(f"{nxt} {token}")
                i += 2
                continue
        names.append(token)
        i += 1
    return names


def parse_authors(segment: str) -> AuthorList:
    """Parse an author segment such as ``"Vaswani, A., Shazeer, N., et al."``."""
    et_al = bool(_ET_AL.search(segment))
    text = _SEPARATOR.sub(";", _ET_AL.sub("", segment))
    tokens = [t for t in map(_clean_token, re.split(r"[;,]", text)) if t]
    tokens = [t for t in tokens if t.lower() not in _SUFFIXES]
    if not tokens:
        return AuthorList(authors=(), et_al=et_al, confidence=0.0)
    candidates = _pair_surname_initials(tokens)
    authors = tuple(a for a in map(parse_name, candidates) if a is not None)
    return AuthorList(authors=authors, et_al=et_al, confidence=len(authors) / len(candidates))
