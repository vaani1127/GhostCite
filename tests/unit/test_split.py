from __future__ import annotations

from ghostcite.parse.split import RawReference, SourceLine, split_references


def _lines(text: str) -> list[SourceLine]:
    return [SourceLine(line, i) for i, line in enumerate(text.split("\n"), 1)]


def _texts(text: str) -> list[str]:
    return [ref.text for ref in split_references(_lines(text))]


def test_bracket_numbering_with_wrapped_lines() -> None:
    text = (
        "[1] A. Vaswani, N. Shazeer. Attention is all\n"
        "you need. NeurIPS, 2017.\n"
        "[2] K. He. Deep residual learn-\n"
        "ing. CVPR, 2016."
    )
    refs = split_references(_lines(text))
    assert refs == [
        RawReference("A. Vaswani, N. Shazeer. Attention is all you need. NeurIPS, 2017.", 1),
        RawReference("K. He. Deep residual learning. CVPR, 2016.", 3),
    ]


def test_dot_numbering_ignores_out_of_sequence_numbers() -> None:
    text = (
        "1. Smith J. A first paper. Journal of\n"
        "2019. Proceedings continued here.\n"  # "2019." is not marker 2
        "2. Doe A. A second paper. Venue, 2020.\n"
        "12. Wrong number on a wrapped line\n"
        "3. Roe B. Third. Venue, 2021."
    )
    texts = _texts(text)
    assert len(texts) == 3
    assert texts[0].startswith("Smith J. A first paper. Journal of 2019.")
    assert texts[1].endswith("12. Wrong number on a wrapped line")


def test_parenthesized_numbering() -> None:
    assert _texts("(1) First ref, 2019.\n(2) Second ref, 2020.") == [
        "First ref, 2019.",
        "Second ref, 2020.",
    ]


def test_noise_before_first_marker_is_dropped() -> None:
    assert _texts("Bibliography noise\n[1] Only ref, 2020.\n[2] Another, 2021.") == [
        "Only ref, 2020.",
        "Another, 2021.",
    ]


def test_inline_bracket_lists_are_exploded() -> None:
    assert _texts("[1] First ref, 2019. [2] Second ref, 2020. [3] Third ref, 2021.") == [
        "First ref, 2019.",
        "Second ref, 2020.",
        "Third ref, 2021.",
    ]


def test_blank_line_separated_blocks() -> None:
    text = (
        "Vaswani, A. (2017). Attention is\nall you need. NeurIPS.\n\n"
        "He, K. (2016). Deep residual\nlearning. CVPR.\n\n"
        "LeCun, Y. (2015). Deep learning. Nature."
    )
    assert _texts(text) == [
        "Vaswani, A. (2017). Attention is all you need. NeurIPS.",
        "He, K. (2016). Deep residual learning. CVPR.",
        "LeCun, Y. (2015). Deep learning. Nature.",
    ]


def test_author_year_one_per_line_with_wraps() -> None:
    text = (
        "Vaswani, A., Shazeer, N. (2017). Attention is all you need. Advances in\n"
        "Neural Information Processing Systems.\n"
        "He K, Zhang X. Deep residual learning. CVPR. 2016.\n"
        "A. Krizhevsky. ImageNet classification. NeurIPS, 2012."
    )
    texts = _texts(text)
    assert len(texts) == 3
    assert texts[0].endswith("Advances in Neural Information Processing Systems.")


def test_stray_blank_line_does_not_merge_one_per_line_list() -> None:
    lines = [f"Author{i}, A. (20{10 + i}). Title number {i}. Venue." for i in range(6)]
    lines.insert(3, "")
    assert len(_texts("\n".join(lines))) == 6


def test_empty_input() -> None:
    assert split_references([]) == []
    assert split_references(_lines("\n  \n")) == []


def test_large_numbered_list() -> None:
    text = "\n".join(f"[{i}] Author{i} A. Title {i}. Venue, 2020." for i in range(1, 251))
    refs = split_references(_lines(text))
    assert len(refs) == 250
    assert refs[-1].text == "Author250 A. Title 250. Venue, 2020."
    assert refs[-1].line == 250


def test_small_numbering_gaps_do_not_merge_references() -> None:
    text = (
        "[1] First ref, 2019.\n[2] Second ref, 2020.\n[4] Fourth ref, 2021.\n[5] Fifth ref, 2022."
    )
    assert _texts(text) == [
        "First ref, 2019.",
        "Second ref, 2020.",
        "Fourth ref, 2021.",
        "Fifth ref, 2022.",
    ]


def test_large_jumps_are_continuation_text() -> None:
    text = "1. First ref, Journal of\n9. Things that wrap, 2019.\n2. Second ref, 2020."
    assert _texts(text) == ["First ref, Journal of 9. Things that wrap, 2019.", "Second ref, 2020."]
