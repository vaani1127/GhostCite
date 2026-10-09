"""Text cleanup shared by every input format."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

# Characters that PDF extractors and word processors leave behind with no visible role.
_INVISIBLE = dict.fromkeys(map(ord, "\u00ad\u200b\u200c\u200d\u2060\ufeff"))
_SPACES = re.compile(r"[ \t\u00a0\u2000-\u200a\u202f\u205f\u3000]+")
_WORD_BEFORE_HYPHEN = re.compile(r"([\w-]+)-$")


def clean_text(text: str) -> str:
    """Normalize unicode and whitespace without changing the meaning of the text.

    NFKC folds typographic ligatures from PDFs (``ﬁ`` → ``fi``) and full-width forms,
    while keeping accented letters intact for display. Matching applies its own,
    stronger normalization later.
    """
    text = unicodedata.normalize("NFKC", text).translate(_INVISIBLE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(_SPACES.sub(" ", line).strip() for line in text.split("\n"))


def join_lines(lines: Iterable[str]) -> str:
    """Join wrapped lines of one reference into a single line.

    A hyphen at a line end is removed when it most likely splits a single word
    ("hyphen-" + "ation"). It is kept, with no space added, when the word already
    contains a hyphen ("state-of-the-" + "art") or when the next line does not start
    with a lowercase letter ("Jean-" + "Pierre", or a DOI split before a digit).
    """
    parts: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        word = _WORD_BEFORE_HYPHEN.search(parts[-1]) if parts else None
        if word is not None:
            splits_word = line[0].islower() and word.group(1).isalpha()
            parts[-1] = (parts[-1][:-1] if splits_word else parts[-1]) + line
            continue
        parts.append(line)
    return " ".join(parts)
