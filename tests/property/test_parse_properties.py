"""Property-based tests: the splitter loses, duplicates and reorders nothing, and no
parser ever crashes on arbitrary input."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ghostcite.parse.cleanup import clean_text, join_lines
from ghostcite.parse.fields import parse_fields
from ghostcite.parse.names import parse_authors
from ghostcite.parse.split import SourceLine, split_references

# Words without digits, brackets or hyphens, so a wrapped line can never look like a
# reference marker and no dehyphenation applies.
_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ\u00e9\u00fc\u00f1.,;:"
_WORD = st.text(alphabet=_ALPHABET, min_size=1, max_size=10)
_REFERENCE = st.lists(_WORD, min_size=1, max_size=25).map(" ".join)
_MARKER_STYLES = st.sampled_from(["[{n}] ", "{n}. ", "({n}) "])


@st.composite
def numbered_lists(draw: st.DrawFn) -> tuple[list[str], list[SourceLine]]:
    references = draw(st.lists(_REFERENCE, min_size=2, max_size=40))
    style = draw(_MARKER_STYLES)
    lines: list[SourceLine] = []
    for n, reference in enumerate(references, 1):
        words = reference.split(" ")
        cut_points = sorted(set(draw(st.lists(st.integers(1, len(words)), max_size=3))))
        chunks, start = [], 0
        for cut in [*cut_points, len(words)]:
            if cut > start:
                chunks.append(" ".join(words[start:cut]))
                start = cut
        lines.append(SourceLine(style.format(n=n) + chunks[0], len(lines) + 1))
        lines.extend(SourceLine(chunk, len(lines) + 1) for chunk in chunks[1:])
    return references, lines


@settings(max_examples=150, deadline=None)
@given(numbered_lists())
def test_numbered_split_recovers_every_reference_in_order(
    case: tuple[list[str], list[SourceLine]],
) -> None:
    references, lines = case
    assert [ref.text for ref in split_references(lines)] == references


@settings(max_examples=200, deadline=None)
@given(st.lists(st.text(max_size=80), max_size=30))
def test_split_never_crashes_and_never_returns_empty_references(texts: list[str]) -> None:
    lines = [SourceLine(clean_text(t).replace("\n", " "), i) for i, t in enumerate(texts, 1)]
    refs = split_references(lines)
    assert all(ref.text.strip() for ref in refs)


@given(st.text(max_size=200))
def test_clean_text_is_idempotent(text: str) -> None:
    once = clean_text(text)
    assert clean_text(once) == once


@given(
    st.lists(st.text(alphabet=st.characters(exclude_characters="-\n"), max_size=30), max_size=10)
)
def test_join_lines_without_hyphens_is_a_space_join(lines: list[str]) -> None:
    expected = " ".join(line.strip() for line in lines if line.strip())
    assert join_lines(lines) == expected


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=300))
def test_parse_fields_never_crashes(raw: str) -> None:
    fields = parse_fields(raw, current_year=2026)
    assert fields.title is None or fields.title.strip() == fields.title
    for author in fields.authors:
        assert author.surname


@given(st.text(max_size=200))
def test_parse_authors_confidence_is_a_fraction(segment: str) -> None:
    result = parse_authors(segment)
    assert 0.0 <= result.confidence <= 1.0
    assert all(author.surname for author in result.authors)
