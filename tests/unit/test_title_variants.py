"""The significant-words rule must not raise false alarms on real, correctly cited titles.

Every pair below is the same work written two legitimate ways. Each must be a title
match, and with agreeing authors and year the verdict must be VERIFIED.
"""

from __future__ import annotations

import pytest

from ghostcite.match.score import is_title_match, match_candidate
from ghostcite.models import Author, Candidate, Engine, ParsedFields, Verdict
from ghostcite.verdict.rules import decide

ELLIPSIS = "…"

SAME_WORK = {
    # Subtitle dropped by the citing author.
    "short_title_bert": (
        "BERT",
        "BERT: Pre-training of deep bidirectional transformers for language understanding",
    ),
    "short_title_two_words": (
        "Wings of Fire",
        "Wings of Fire: An Autobiography",
    ),
    "subtitle_after_dash": (
        "Scikit-learn",
        "Scikit-learn - Machine learning in Python",
    ),
    # Scholar truncates long titles with an ellipsis, sometimes mid-word.
    "scholar_truncated": (
        "Preferred reporting items for systematic reviews and meta-analyses: the PRISMA statement",
        "Preferred reporting items for systematic reviews and meta-analyses: "
        f"the PRISMA {ELLIPSIS}",
    ),
    "scholar_truncated_mid_word": (
        "Analysis of relative gene expression data using real-time quantitative PCR",
        f"Analysis of relative gene expression data using real-time quanti{ELLIPSIS}",
    ),
    "ascii_ellipsis": (
        "Mastering the game of Go with deep neural networks and tree search",
        "Mastering the game of Go with deep neural networks and ...",
    ),
    # Hyphenation and spacing.
    "pretraining": ("Pre-training of deep transformers", "Pretraining of deep transformers"),
    "pre_space_training": (
        "Pre training of deep transformers",
        "Pre-training of deep transformers",
    ),
    "realtime": ("Real time object detection", "Real-time object detection"),
    "email": ("Spam filtering for e-mail", "Spam filtering for email"),
    "deeplearning": ("Deeplearning for medical imaging", "Deep learning for medical imaging"),
    # British and American spelling.
    "optimisation": ("Stochastic optimisation methods", "Stochastic optimization methods"),
    "colour": ("Colour constancy in natural images", "Color constancy in natural images"),
    "centre": ("A centre for fibre optics", "A center for fiber optics"),
    "behaviour": ("Modelling consumer behaviour", "Modeling consumer behavior"),
    "analyse": ("How to analyse labelled data", "How to analyze labeled data"),
    "haemoglobin": ("Haemoglobin levels in anaemia", "Hemoglobin levels in anemia"),
    # Digits and number words.
    "two_stream": (
        "Two-stream networks for action recognition",
        "2-stream networks for action recognition",
    ),
    "third": (
        "The 3rd international survey of methods",
        "The third international survey of methods",
    ),
    "ten_years": ("Ten years of graph learning", "10 years of graph learning"),
    # LaTeX and typographic remnants.
    "latex_braces": (
        "{BERT}: Pre-training of deep transformers",
        "BERT: Pre-training of deep transformers",
    ),
    "latex_accent": ('{\\"U}ber die Bedeutung von Daten', "Über die Bedeutung von Daten"),
    "latex_greek": ("The $\\alpha$-helix in proteins", "The α-helix in proteins"),  # noqa: RUF001 - a real Greek alpha is the point of this case
    "curly_quotes": (
        "The market for “lemons”: quality uncertainty",
        'The market for "lemons": quality uncertainty',
    ),
    "latex_emph": ("A study of \\emph{deep} networks", "A study of deep networks"),
}


@pytest.mark.parametrize(("cited", "found"), SAME_WORK.values(), ids=SAME_WORK.keys())
def test_variants_are_title_matches(cited: str, found: str) -> None:
    assert is_title_match(cited, found)


@pytest.mark.parametrize(("cited", "found"), SAME_WORK.values(), ids=SAME_WORK.keys())
def test_variants_are_verified(cited: str, found: str) -> None:
    fields = ParsedFields(title=cited, authors=(Author(surname="Rao"),), year=2019)
    candidate = Candidate(
        engine=Engine.GOOGLE_SCHOLAR, title=found, authors=("A Rao",), year=2019, query="q"
    )
    decision = decide(
        fields, match_candidate(fields, candidate), complete=True, incomplete_reason=""
    )
    assert decision.verdict is Verdict.VERIFIED, decision.reason


DIFFERENT_WORK = {
    "replaced_word": ("Attention is all we need", "Attention is all you need"),
    "added_word": ("Attention is all you need now", "Attention is all you need"),
    "different_number": (
        "Two-stream networks for action recognition",
        "3-stream networks for action recognition",
    ),
    "different_subtitle": ("Deep learning: a review", "Deep learning: methods and applications"),
    "single_letter_main_title": ("A", "A: a study of everything"),
    "british_lookalike": ("Four hours of tours", "For hors of tors"),
}


@pytest.mark.parametrize(("cited", "found"), DIFFERENT_WORK.values(), ids=DIFFERENT_WORK.keys())
def test_real_differences_are_still_caught(cited: str, found: str) -> None:
    assert not is_title_match(cited, found)


def test_spaced_and_greek_formula_notation_agree() -> None:
    assert is_title_match(
        "Real-time quantitative PCR and the 2(-Delta Delta C(T)) method",
        "Real-time quantitative PCR and the 2−ΔΔCT method",  # noqa: RUF001 - a real minus sign is the point of this case
    )
