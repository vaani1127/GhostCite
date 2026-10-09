from __future__ import annotations

import pytest

from ghostcite.parse.names import is_initials, parse_authors, parse_name


def _surnames(segment: str) -> list[str]:
    return [a.surname for a in parse_authors(segment).authors]


@pytest.mark.parametrize("word", ["A.", "A", "AK", "A.K.", "J.-P.", "J-P", "R.K."])
def test_initials(word: str) -> None:
    assert is_initials(word)


@pytest.mark.parametrize("word", ["Ab", "Vaswani", "a.", "ABCDE", "1."])
def test_not_initials(word: str) -> None:
    assert not is_initials(word)


@pytest.mark.parametrize(
    ("segment", "expected"),
    [
        ("Vaswani, A., Shazeer, N., & Parmar, N.", ["Vaswani", "Shazeer", "Parmar"]),
        ("Vaswani A, Shazeer N, Parmar N", ["Vaswani", "Shazeer", "Parmar"]),
        ("A. Vaswani, N. Shazeer, and N. Parmar", ["Vaswani", "Shazeer", "Parmar"]),
        ("Ashish Vaswani and Noam Shazeer", ["Vaswani", "Shazeer"]),
        ("Vaswani, Ashish, Shazeer, Noam", ["Vaswani", "Shazeer"]),
        ("Sharma AK, Gupta RK", ["Sharma", "Gupta"]),
        ("R. K. Narayan, A. P. J. Abdul Kalam", ["Narayan", "Abdul Kalam"]),
        ("Jean de la Fontaine", ["de la Fontaine"]),
        ("Ludwig van Beethoven & John F. Kennedy", ["van Beethoven", "Kennedy"]),
        ("M\u00fcller, J., & \u00d1\u00fa\u00f1ez, P.", ["M\u00fcller", "\u00d1\u00fa\u00f1ez"]),
        ("O'Brien, T. and D'Souza, R.", ["O'Brien", "D'Souza"]),
        ("Chang, M.-W., Lee, K.", ["Chang", "Lee"]),
        ("Smith, J., Jr., Doe, A.", ["Smith", "Doe"]),
        ("World Health Organization", ["Organization"]),
    ],
)
def test_author_formats(segment: str, expected: list[str]) -> None:
    assert _surnames(segment) == expected


def test_initials_are_kept_as_given_names() -> None:
    authors = parse_authors("Sharma AK, R. K. Narayan").authors
    assert [(a.surname, a.given) for a in authors] == [("Sharma", "AK"), ("Narayan", "R. K.")]


@pytest.mark.parametrize(
    "segment",
    [
        "Vaswani A, Shazeer N, et al.",
        "Brown, T. B. et al",
        "Vaswani, A. and others",
        "X Y, et. al.",
    ],
)
def test_et_al_detected_and_removed(segment: str) -> None:
    result = parse_authors(segment)
    assert result.et_al
    assert all("al" not in a.surname for a in result.authors)


def test_confidence_reflects_unparseable_parts() -> None:
    result = parse_authors("Vaswani A, the transformer model is great")
    assert [a.surname for a in result.authors] == ["Vaswani"]
    assert result.confidence == 0.5


def test_empty_segment() -> None:
    result = parse_authors(" , ; ")
    assert result.authors == ()
    assert result.confidence == 0.0


@pytest.mark.parametrize(
    "text",
    [
        "",
        "A.",  # a lone initial
        "deep learning",  # lowercase words
        "Hinton G. Deep Learning",  # an initial in the middle of a title
        "G. Hinton. Deep Learning",  # ran into the next sentence
        "Toutanova K.: BERT",  # punctuation that never appears in names
        "One Two Three Four Five Six",  # too many words
        "van der",  # only particles
        "AB CD",  # only initials
        "Smith 2019",  # digits
    ],
)
def test_not_a_name(text: str) -> None:
    assert parse_name(text) is None


def test_single_word_names() -> None:
    kalidasa = parse_name("Kalidasa")
    assert kalidasa is not None
    assert kalidasa.surname == "Kalidasa"
    ibm = parse_name("IBM")
    assert ibm is not None
    assert ibm.surname == "IBM"


def test_initials_both_before_and_inside_a_name_are_rejected() -> None:
    assert parse_name("A. Smith B. Jones") is None
