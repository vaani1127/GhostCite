from __future__ import annotations

import pytest

from ghostcite.config import MatchConfig
from ghostcite.match.normalize import fold, main_title, surname_key, tokens
from ghostcite.match.score import (
    best_match,
    combine,
    compare_authors,
    compare_doi,
    compare_venue,
    compare_year,
    match_candidate,
    title_similarity,
    venue_similarity,
)
from ghostcite.models import (
    Author,
    Candidate,
    Engine,
    FieldMatch,
    FieldName,
    FieldStatus,
    ParsedFields,
)

RESNET = "Deep residual learning for image recognition"
NEURIPS = "Advances in neural information processing systems"


def _authors(*surnames: str) -> tuple[Author, ...]:
    return tuple(Author(surname=s) for s in surnames)


def _candidate(**kwargs: object) -> Candidate:
    defaults: dict[str, object] = {
        "engine": Engine.GOOGLE_SCHOLAR,
        "title": "Attention is all you need",
        "authors": ("A Vaswani", "N Shazeer", "N Parmar"),
        "authors_truncated": True,
        "year": 2017,
        "venue": "Advances in neural",
        "venue_truncated": True,
        "query": "q",
    }
    return Candidate.model_validate({**defaults, **kwargs})


# ---------------------------------------------------------------- normalize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Über die Bedeutung!", "uber die bedeutung"),
        ("Deep  Learning: A Review", "deep learning a review"),
        ("Straße & Co.", "strasse and co"),
        (r"\emph{Neural} networks", "neural networks"),
        ("snake_case-words", "snake case words"),
        ("", ""),
    ],
)
def test_fold(text: str, expected: str) -> None:
    assert fold(text) == expected


def test_tokens_and_stopwords() -> None:
    assert tokens("The Anatomy of a Search Engine", drop_stopwords=True) == [
        "anatomy",
        "search",
        "engine",
    ]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("BERT: Pre-training of deep transformers", "BERT"),
        ("Wings of Fire - An Autobiography", "Wings of Fire"),
        ("No subtitle here", "No subtitle here"),
    ],
)
def test_main_title(title: str, expected: str) -> None:
    assert main_title(title) == expected


def test_surname_key() -> None:
    assert surname_key("A. P. J. Abdul Kalam") == "kalam"
    assert surname_key("Müller") == "muller"
    assert surname_key("") == ""


# ---------------------------------------------------------------- title


@pytest.mark.parametrize(
    ("cited", "found", "minimum", "maximum"),
    [
        ("Attention is all you need", "Attention Is All You Need", 1.0, 1.0),
        ("Attention is all you need.", "Attention is all you need", 1.0, 1.0),
        (RESNET, RESNET.replace("recognition", "recognitoin"), 0.95, 1.0),
        ("Wings of Fire: An Autobiography", "Wings of Fire", 0.9, 0.9),
        ("Wings of Fire", "Wings of Fire: An Autobiography", 0.9, 0.9),
        ("Deep learning", "Deep learning in medicine: a review", 0.0, 0.6),
        ("Attention is all you need", "Quantum gradient folding", 0.0, 0.4),
        ("", "Anything", 0.0, 0.0),
    ],
)  # fmt: skip
def test_title_similarity(cited: str, found: str, minimum: float, maximum: float) -> None:
    assert minimum <= title_similarity(cited, found) <= maximum


def test_single_word_main_title_does_not_count_as_dropped_subtitle() -> None:
    # "BERT" alone is too short to identify "BERT: Pre-training ..." with confidence.
    assert title_similarity("BERT", "BERT: Pre-training of deep transformers") < 0.9


# ---------------------------------------------------------------- authors


def test_authors_match_with_truncation() -> None:
    field = compare_authors(
        _authors("Vaswani", "Shazeer", "Parmar", "Uszkoreit"),
        ("A Vaswani", "N Shazeer", "N Parmar"),
        True,
    )
    assert (field.status, field.score) == (FieldStatus.MATCH, 1.0)


def test_untruncated_list_must_contain_every_cited_author() -> None:
    field = compare_authors(_authors("Vaswani", "Uszkoreit"), ("A Vaswani", "N Shazeer"), False)
    assert (field.status, field.score) == (FieldStatus.PARTIAL, 0.5)


def test_swapped_authors_mismatch() -> None:
    field = compare_authors(_authors("Hinton", "Bengio"), ("A Vaswani", "N Shazeer"), False)
    assert field.status is FieldStatus.MISMATCH
    assert field.cited == "Hinton, Bengio"
    assert field.found == "A Vaswani, N Shazeer"


def test_transliterated_and_indian_surnames() -> None:
    assert compare_authors(_authors("Mueller"), ("J Müller",), False).status is FieldStatus.MATCH
    kalam = compare_authors(_authors("Abdul Kalam"), ("A. P. J. Abdul Kalam", "Arun Tiwari"), False)
    assert kalam.status is FieldStatus.MATCH


def test_short_surnames_must_match_exactly() -> None:
    assert compare_authors(_authors("Li"), ("Y Lu",), False).status is FieldStatus.MISMATCH


def test_missing_authors_are_unknown() -> None:
    assert compare_authors((), ("A Vaswani",), False).status is FieldStatus.UNKNOWN
    assert compare_authors(_authors("Vaswani"), (), False).status is FieldStatus.UNKNOWN


# ---------------------------------------------------------------- year, venue, doi


@pytest.mark.parametrize(
    ("cited", "found", "status", "score"),
    [
        (2017, 2017, FieldStatus.MATCH, 1.0),
        (2018, 2017, FieldStatus.PARTIAL, 0.8),
        (2021, 2019, FieldStatus.MISMATCH, 0.0),
        (None, 2019, FieldStatus.UNKNOWN, None),
        (2019, None, FieldStatus.UNKNOWN, None),
    ],
)
def test_compare_year(
    cited: int | None, found: int | None, status: FieldStatus, score: float | None
) -> None:
    field = compare_year(cited, found)
    assert (field.status, field.score) == (status, score)


@pytest.mark.parametrize(
    ("cited", "found", "status"),
    [
        ("Adv Neural Inf Process Syst", NEURIPS, FieldStatus.MATCH),
        (NEURIPS.title(), "Advances in neural", FieldStatus.MATCH),
        ("Nature", "nature", FieldStatus.MATCH),
        ("NeurIPS", NEURIPS, FieldStatus.UNKNOWN),
        ("Journal of Imaginary Computing Letters", NEURIPS, FieldStatus.MISMATCH),
        ("Proc. IEEE CVPR", "of the IEEE conference on computer", FieldStatus.UNKNOWN),
        (None, "Nature", FieldStatus.UNKNOWN),
    ],
)  # fmt: skip
def test_compare_venue(cited: str | None, found: str | None, status: FieldStatus) -> None:
    assert compare_venue(cited, found).status is status


def test_venue_similarity_ignores_generic_words() -> None:
    assert venue_similarity("Proceedings of the conference", "Journal") == 0.0


def test_compare_doi() -> None:
    linked = _candidate(link="https://doi.org/10.1038/nature14539")
    assert compare_doi("10.1038/nature14539", linked).status is FieldStatus.MATCH
    assert compare_doi("10.1/other", linked).status is FieldStatus.UNKNOWN
    assert compare_doi(None, linked).status is FieldStatus.UNKNOWN


# ---------------------------------------------------------------- combine and best match


def test_combine_renormalizes_over_judged_fields() -> None:
    fields = (
        FieldMatch(field=FieldName.TITLE, status=FieldStatus.MATCH, score=1.0),
        FieldMatch(field=FieldName.YEAR, status=FieldStatus.MISMATCH, score=0.0),
        FieldMatch(field=FieldName.VENUE, status=FieldStatus.UNKNOWN, score=0.2),
    )
    cfg = MatchConfig()
    expected = cfg.weight_title / (cfg.weight_title + cfg.weight_year)
    assert combine(fields, Engine.GOOGLE_SCHOLAR) == pytest.approx(expected, abs=1e-4)


def test_combine_applies_doi_boost_and_fallback_cap() -> None:
    weak = (
        FieldMatch(field=FieldName.TITLE, status=FieldStatus.PARTIAL, score=0.5),
        FieldMatch(field=FieldName.DOI, status=FieldStatus.MATCH, score=1.0),
    )
    assert combine(weak, Engine.GOOGLE_SCHOLAR) == 0.98
    assert combine(weak, Engine.GOOGLE) == 0.7
    assert combine((), Engine.GOOGLE_SCHOLAR) == 0.0


def test_match_candidate_end_to_end() -> None:
    fields = ParsedFields(
        title="Attention is all you need", authors=_authors("Vaswani"), year=2019, venue="NeurIPS"
    )
    result = match_candidate(fields, _candidate())
    statuses = {f.field: f.status for f in result.fields}
    assert statuses[FieldName.TITLE] is FieldStatus.MATCH
    assert statuses[FieldName.YEAR] is FieldStatus.MISMATCH
    assert statuses[FieldName.VENUE] is FieldStatus.UNKNOWN
    assert 0 < result.confidence < 1


@pytest.mark.parametrize(
    ("title", "status"),
    [
        ("Attention is all you need", FieldStatus.MATCH),
        ("Attention is all we need now", FieldStatus.PARTIAL),
        ("Unrelated words entirely", FieldStatus.MISMATCH),
    ],
)  # fmt: skip
def test_title_status_bands(title: str, status: FieldStatus) -> None:
    result = match_candidate(ParsedFields(title=title), _candidate())
    field = result.field(FieldName.TITLE)
    assert field is not None
    assert field.status is status


def test_best_match_prefers_the_original_over_lookalikes() -> None:
    fields = ParsedFields(title="Attention is all you need", authors=_authors("Vaswani"), year=2017)
    notes = _candidate(
        title="Attention is all you need",
        authors=("Some Student",),
        authors_truncated=False,
        year=2023,
        cited_by=7,
    )
    original = _candidate(cited_by=274_507)
    other = _candidate(title="Tensor product attention is all you need", year=2026)
    results = [match_candidate(fields, c) for c in (notes, other, original)]
    best = best_match(results)
    assert best is not None
    assert best.candidate.cited_by == 274_507


def test_best_match_falls_back_to_closest_title() -> None:
    fields = ParsedFields(title="Attention is all you need")
    far = match_candidate(fields, _candidate(title="Completely different topic"))
    near = match_candidate(fields, _candidate(title="Attention is mostly what you need"))
    assert best_match([far, near]) is near
    assert best_match([]) is None
