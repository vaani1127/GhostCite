"""Normalization for comparing citation text with search results.

Comparison text is folded hard: Unicode NFKD, diacritics removed, case folded,
punctuation and LaTeX commands dropped, whitespace collapsed. "Über die Bedeutung" and
"Uber die bedeutung" compare equal, and so does the LaTeX-escaped spelling. This text is
only used for scoring and never shown to users.
"""

from __future__ import annotations

import re
import unicodedata

# Words that carry no identity in titles or venues.
STOPWORDS = frozenset(
    {
        *("a", "an", "the", "of", "for", "and", "in", "on", "to", "with", "by", "at"),
        *("from", "into", "via", "its", "as", "or", "le", "la", "les", "de", "der", "die"),
    }
)
_LATEX_COMMAND = re.compile(r"\\[a-zA-Z]+\s*")
_NON_WORD = re.compile(r"[^\w\s]|_")
_SPACES = re.compile(r"\s+")
_SUBTITLE_SPLIT = re.compile(r"\s*(?::|\s[-\u2013\u2014]\s|\?\s)\s*")
# Transliterations that NFKD alone does not produce ("Müller" vs "Mueller").
_GERMANIC = str.maketrans(
    {"\u00df": "ss", "\u00e6": "ae", "\u0153": "oe", "\u00f8": "o", "\u0142": "l"}
)


def fold(text: str) -> str:
    """Lowercase ASCII-ish form: NFKD, without diacritics, LaTeX commands or punctuation."""
    text = _LATEX_COMMAND.sub(" ", text.translate(_GERMANIC))
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    stripped = stripped.casefold().replace("&", " and ")
    return _SPACES.sub(" ", _NON_WORD.sub(" ", stripped)).strip()


def tokens(text: str, *, drop_stopwords: bool = False) -> list[str]:
    """Folded words of ``text``, optionally without stopwords."""
    words = fold(text).split()
    return [w for w in words if w not in STOPWORDS] if drop_stopwords else words


def main_title(title: str) -> str:
    """The part of a title before its subtitle ("BERT: Pre-training …" → "BERT")."""
    return _SUBTITLE_SPLIT.split(title.strip(), maxsplit=1)[0]


def surname_key(name: str) -> str:
    """Comparable surname: the last folded word ("A. P. J. Abdul Kalam" → "kalam")."""
    words = fold(name).split()
    return words[-1] if words else ""
