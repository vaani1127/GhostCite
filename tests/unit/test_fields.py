from __future__ import annotations

from dataclasses import dataclass

import pytest

from ghostcite.config import ParseConfig
from ghostcite.parse.fields import find_doi, find_venue, find_year, guess_entry_type, parse_fields

YEAR = 2026


@dataclass(frozen=True)
class Case:
    raw: str
    title: str | None
    surnames: list[str]
    year: int | None
    venue: str | None = None
    doi: str | None = None
    et_al: bool = False


CASES = {
    "ieee_quoted": Case(
        'A. Vaswani, N. Shazeer, N. Parmar, et al., "Attention is all you need," in Advances in '
        "Neural Information Processing Systems, 2017, pp. 5998-6008.",
        "Attention is all you need",
        ["Vaswani", "Shazeer", "Parmar"],
        2017,
        "Advances in Neural Information Processing Systems",
        et_al=True,
    ),
    "ieee_curly_quotes": Case(
        "K. He, X. Zhang, \u201cDeep residual learning for image recognition,\u201d "
        "in Proc. CVPR, 2016.",
        "Deep residual learning for image recognition",
        ["He", "Zhang"],
        2016,
        "Proc. CVPR",
    ),
    "apa": Case(
        "Vaswani, A., Shazeer, N., & Parmar, N. (2017). Attention is all you need. Advances in "
        "Neural Information Processing Systems, 30, 5998-6008.",
        "Attention is all you need",
        ["Vaswani", "Shazeer", "Parmar"],
        2017,
        "Advances in Neural Information Processing Systems",
    ),
    "acm": Case(
        "Ashish Vaswani, Noam Shazeer, and Niki Parmar. 2017. Attention is all you need. In "
        "Proceedings of NeurIPS. 5998-6008.",
        "Attention is all you need",
        ["Vaswani", "Shazeer", "Parmar"],
        2017,
        "Proceedings of NeurIPS",
    ),
    "vancouver": Case(
        "Vaswani A, Shazeer N, Parmar N, et al. Attention is all you need. Adv Neural Inf "
        "Process Syst. 2017;30:5998-6008.",
        "Attention is all you need",
        ["Vaswani", "Shazeer", "Parmar"],
        2017,
        "Adv Neural Inf Process Syst",
        et_al=True,
    ),
    "springer_lncs": Case(
        "Devlin, J., Chang, M.-W., Lee, K., Toutanova, K.: BERT: Pre-training of deep "
        "bidirectional transformers for language understanding. In: NAACL-HLT (2019)",
        "BERT: Pre-training of deep bidirectional transformers for language understanding",
        ["Devlin", "Chang", "Lee", "Toutanova"],
        2019,
        "NAACL-HLT",
    ),
    "vancouver_with_doi": Case(
        "LeCun Y, Bengio Y, Hinton G. Deep learning. Nature. 2015;521(7553):436-44. "
        "https://doi.org/10.1038/nature14539",
        "Deep learning",
        ["LeCun", "Bengio", "Hinton"],
        2015,
        "Nature",
        doi="10.1038/nature14539",
    ),
    "indian_journal": Case(
        "Sharma AK, Gupta RK. Prevalence of hypertension in rural Punjab. Indian J Med Res. "
        "2019;149(2):123-30.",
        "Prevalence of hypertension in rural Punjab",
        ["Sharma", "Gupta"],
        2019,
        "Indian J Med Res",
    ),
    "indian_book": Case(
        "R. K. Narayan, A. P. J. Abdul Kalam. Wings of Fire: An Autobiography. Universities "
        "Press, 1999.",
        "Wings of Fire: An Autobiography",
        ["Narayan", "Abdul Kalam"],
        1999,
        "Universities Press",
    ),
    "diacritics_and_year_suffix": Case(
        "M\u00fcller, J., & \u00d1\u00fa\u00f1ez, P. (2020a). \u00dcber die Bedeutung von Daten. "
        "Zeitschrift f\u00fcr Informatik, 12(3), 45-67.",
        "\u00dcber die Bedeutung von Daten",
        ["M\u00fcller", "\u00d1\u00fa\u00f1ez"],
        2020,
        "Zeitschrift f\u00fcr Informatik",
    ),
    "arxiv_preprint": Case(
        "Brown, T. B. et al. Language models are few-shot learners. arXiv preprint "
        "arXiv:2005.14165 (2020).",
        "Language models are few-shot learners",
        ["Brown"],
        2020,
        "arXiv",
        et_al=True,
    ),
    "doi_prefix_and_missing_year": Case(
        "He K, Zhang X, Ren S, Sun J. Deep residual learning for image recognition. In: "
        "Proceedings of the IEEE CVPR. doi:10.1109/CVPR.2016.90",
        "Deep residual learning for image recognition",
        ["He", "Zhang", "Ren", "Sun"],
        None,
        "Proceedings of the IEEE CVPR",
        doi="10.1109/cvpr.2016.90",
    ),
}


@pytest.mark.parametrize("case", CASES.values(), ids=CASES.keys())
def test_citation_styles(case: Case) -> None:
    fields = parse_fields(case.raw, current_year=YEAR)
    assert fields.title == case.title
    assert [a.surname for a in fields.authors] == case.surnames
    assert fields.year == case.year
    assert fields.venue == case.venue
    assert fields.doi == case.doi
    assert fields.et_al is case.et_al


def test_confidence_reflects_strategy() -> None:
    quoted = parse_fields(CASES["ieee_quoted"].raw, current_year=YEAR).confidence
    apa = parse_fields(CASES["apa"].raw, current_year=YEAR).confidence
    vancouver = parse_fields(CASES["vancouver"].raw, current_year=YEAR).confidence
    assert quoted.title > apa.title > vancouver.title > 0
    assert apa.year == 0.95  # parenthesized
    assert vancouver.doi == 0.0


def test_no_title_when_reference_is_only_author_and_year() -> None:
    fields = parse_fields("Smith J. 2010.", current_year=YEAR)
    assert fields.title is None
    assert fields.confidence.title == 0.0
    assert fields.year == 2010
    assert [a.surname for a in fields.authors] == ["Smith"]


def test_title_without_recognizable_authors_falls_back_to_first_sentence() -> None:
    fields = parse_fields("the anatomy of a large-scale hypertextual web search engine. 1998.")
    assert fields.title == "the anatomy of a large-scale hypertextual web search engine"
    assert fields.confidence.title == 0.3


@pytest.mark.parametrize("raw", ["", "   ", "https://example.org/paper.pdf"])
def test_empty_or_noise_only(raw: str) -> None:
    fields = parse_fields(raw)
    assert fields.title is None
    assert fields.authors == ()


def test_doi_only_reference_keeps_the_doi() -> None:
    fields = parse_fields("doi:10.1145/3292500.3330701")
    assert fields.doi == "10.1145/3292500.3330701"
    assert fields.title is None


def test_short_fragment_is_not_a_title() -> None:
    assert parse_fields('"Short," 2020.').title is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("see https://doi.org/10.1038/NATURE14539.", "10.1038/nature14539"),
        ("doi: 10.1000/xyz123),", "10.1000/xyz123"),
        ("no identifier here", None),
    ],
)
def test_find_doi(text: str, expected: str | None) -> None:
    assert find_doi(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Smith, J. (2019). Title. Venue, 2020.", 2019),  # parenthesized wins
        ("Smith, J. 2018. Title. In Proc. 2019.", 2018),  # year after the authors
        ("J. Smith, Title, Venue, vol. 3, 2017.", 2017),  # last year (IEEE)
        ("Title. Venue 12, pp. 1999-2005.", None),  # page range, not a year
        ("Old work, 1650.", None),  # before min_year
        ("In press, 2027.", 2027),  # next year allowed
        ("Future, 2031.", None),
    ],
)
def test_find_year(text: str, expected: int | None) -> None:
    year = find_year(text, current_year=YEAR)
    assert (year.value if year else None) == expected


def test_find_year_confidence_drops_with_conflicting_years() -> None:
    single = find_year("A. B. Title, 2017.", current_year=YEAR)
    conflicting = find_year("A. B. Title, 2017. Reprinted 2019.", current_year=YEAR)
    assert single is not None
    assert conflicting is not None
    assert single.confidence > conflicting.confidence


def test_find_year_respects_config() -> None:
    assert find_year("Classic, 1850.", ParseConfig(min_year=1900), current_year=YEAR) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (". In: NIPS, pp. 1-9 (2017)", "NIPS"),
        (
            ", IEEE Trans. Pattern Anal. Mach. Intell., 35(8), 1798-1828",
            "IEEE Trans. Pattern Anal. Mach. Intell",
        ),
        (". arXiv preprint arXiv:1810.04805", "arXiv"),
        (". 2019.", None),
        ("", None),
    ],
)
def test_find_venue(text: str, expected: str | None) -> None:
    assert find_venue(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Kumar S. Economic reforms. PhD thesis, University of Delhi, 2018.", "phdthesis"),
        ("Rao P. A study. M.Tech dissertation, IIT Bombay.", "phdthesis"),
        ("Doe J. Systems. Technical Report TR-12, 2001.", "techreport"),
        ("Goodfellow I. Deep Learning. MIT Press; 2016.", "book"),
        ("Vaswani A. Attention is all you need. NeurIPS 2017.", None),
    ],
)
def test_guess_entry_type(text: str, expected: str | None) -> None:
    assert guess_entry_type(text) == expected


def test_year_inside_author_segment_is_not_part_of_the_authors() -> None:
    fields = parse_fields(
        'Smith, J., 2019, "A study of citation errors," Venue.', current_year=YEAR
    )
    assert fields.title == "A study of citation errors"
    assert [a.surname for a in fields.authors] == ["Smith"]
    assert fields.year == 2019


def test_overlong_author_lists_stop_the_author_scan() -> None:
    authors = ", ".join(f"Author{chr(65 + i % 26)}{chr(65 + i // 26)} A" for i in range(80))
    fields = parse_fields(f"{authors}. A very long collaboration paper. Physics Letters B. 2012.")
    assert fields.title is not None
