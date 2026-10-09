"""Normalization for comparing citation text with search results.

Comparison text is folded hard: LaTeX accents, braces and commands are resolved, Unicode
is decomposed (NFKD) and diacritics removed, case is folded, punctuation dropped and
whitespace collapsed. "Über die Bedeutung", "Uber die bedeutung" and the LaTeX-escaped
spelling all compare equal.

Titles get one more step, :func:`canonical_words`. It joins hyphenated words, writes
numbers as digits and applies a few conservative British-to-American spelling rules, so
legitimate variants of one title never look like a reworded title. This text is only
used for scoring and never shown to users.
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
_GREEK_NAMES = (
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa",
    "lambda", "mu", "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon", "phi",
    "chi", "psi", "omega",
)  # fmt: skip
# Lowercase Greek letters alpha (U+03B1) to omega (U+03C9), without final sigma (U+03C2).
_GREEK_LETTERS = dict(
    zip(
        [chr(code) for code in range(0x03B1, 0x03CA) if code != 0x03C2],
        _GREEK_NAMES,
        strict=True,
    )
)
_LATEX_GREEK = re.compile(r"\\(" + "|".join(_GREEK_NAMES) + r")(?![a-zA-Z])", re.IGNORECASE)
# \"{U}, \'e, \^{o}, \c{c}: keep the letter; its accent goes away with the diacritics anyway.
_LATEX_ACCENT = re.compile(r"\\[`'^\"~=.uvHtcdbk]\s*\{?\s*([A-Za-z])\s*\}?")
_LATEX_COMMAND = re.compile(r"\\[a-zA-Z]+\s*")
_NON_WORD = re.compile(r"[^\w\s]|_")
_SPACES = re.compile(r"\s+")
_SUBTITLE_SPLIT = re.compile(r"\s*(?::|\s[-\u2013\u2014]\s|\?\s)\s*")
_INNER_HYPHEN = re.compile(r"(?<=\w)[-\u2010\u2011](?=\w)")
# A letters-only placeholder survives folding and marks where a hyphen joined two words.
_JOIN = "zqxjoinzqx"
# Transliterations that NFKD alone does not produce.
_GERMANIC = str.maketrans(
    {"\u00df": "ss", "\u00e6": "ae", "\u0153": "oe", "\u00f8": "o", "\u0142": "l"}
)
_NUMBER_WORDS = {
    name: str(value)
    for value, name in enumerate(
        [
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
            "twenty",
        ]
    )
}
_ORDINALS = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th",
    "sixth": "6th", "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th",
}  # fmt: skip
# Conservative British -> American rules, applied only to words of at least
# _MIN_SPELLING_WORD letters, so short words ("hour", "four", "tour") never change.
_SPELLING = (
    (re.compile(r"(?<=\w\w)is(ation|ations|e|es|ed|ing|er|ers)$"), r"iz\1"),  # optimisation
    (re.compile(r"(?<=\w\w)ys(e|es|ed|ing)$"), r"yz\1"),  # analyse
    (re.compile(r"^(\w{3,})our(s|ed|ing|al)?$"), r"\1or\2"),  # colour, behaviour
    (re.compile(r"^(\w+)(t|b)re(s|d)?$"), r"\1\2er\3"),  # centre, theatre
    (re.compile(r"^(\w*[aeiou])ll(ed|ing|er|ers)$"), r"\1l\2"),  # modelled, labelled
    (re.compile(r"(?<=\w)(?:ae|oe)(?=\w{3,})|^(?:ae|oe)(?=\w{4,})"), "e"),  # haemoglobin
)
_MIN_SPELLING_WORD = 6


def _resolve_latex(text: str) -> str:
    text = _LATEX_GREEK.sub(lambda m: f" {m.group(1).lower()} ", text)
    text = _LATEX_ACCENT.sub(r"\1", text)
    text = _LATEX_COMMAND.sub(" ", text)
    return text.replace("{", "").replace("}", "").replace("$", " ")


def fold(text: str) -> str:
    """Lowercase ASCII-ish form: no LaTeX, diacritics or punctuation; Greek letters named."""
    text = _resolve_latex(text.translate(_GERMANIC))
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    stripped = stripped.casefold().replace("&", " and ")
    stripped = "".join(f" {_GREEK_LETTERS[ch]} " if ch in _GREEK_LETTERS else ch for ch in stripped)
    return _SPACES.sub(" ", _NON_WORD.sub(" ", stripped)).strip()


def tokens(text: str, *, drop_stopwords: bool = False) -> list[str]:
    """Folded words of ``text``, optionally without stopwords."""
    words = fold(text).split()
    return [w for w in words if w not in STOPWORDS] if drop_stopwords else words


def canonical_word(word: str) -> str:
    """One folded word in canonical form: digits for numbers, American spelling."""
    if word in _NUMBER_WORDS:
        return _NUMBER_WORDS[word]
    if word in _ORDINALS:
        return _ORDINALS[word]
    if len(word) >= _MIN_SPELLING_WORD:
        for pattern, replacement in _SPELLING:
            word = pattern.sub(replacement, word)
    return word


def canonical_words(title: str) -> list[str]:
    """Title words for comparison: folded, numbers as digits, US spelling, hyphens joined.

    Both sides of a comparison go through the same steps, so "Two-stream", "2-stream"
    and "2stream" agree, and so do "colour"/"color" and "centre"/"center".
    """
    words = fold(_INNER_HYPHEN.sub(f" {_JOIN} ", title)).split()
    result: list[str] = []
    glue = False
    letters = False  # the last token is a run of single letters ("c t" -> "ct")
    for word in words:
        if word == _JOIN:
            glue = bool(result)
            continue
        canonical = canonical_word(word)
        single = len(canonical) == 1 and canonical.isalpha()
        if glue or (single and letters):
            result[-1] += canonical
        else:
            result.append(canonical)
        letters = single and (letters or not glue)
        glue = False
    return result


def main_title(title: str) -> str:
    """The part of a title before its subtitle ("BERT: Pre-training …" → "BERT")."""
    return _SUBTITLE_SPLIT.split(title.strip(), maxsplit=1)[0]


def surname_key(name: str) -> str:
    """Comparable surname: the last folded word ("A. P. J. Abdul Kalam" → "kalam")."""
    words = fold(name).split()
    return words[-1] if words else ""
