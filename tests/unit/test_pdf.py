from __future__ import annotations

import pytest

from ghostcite.config import IngestConfig
from ghostcite.errors import InputError, ScannedPdfError
from ghostcite.ingest.pdf import has_pdf_magic, pdf_lines, pdf_text_pages, remove_running_lines
from tests.pdf_factory import build_pdf, image_only, single_column, two_column_interleaved

BODY = [f"Body sentence number {i} with enough words to look like real text." for i in range(8)]


def _texts(data: bytes) -> list[str]:
    return [line.text for line in pdf_lines(data)]


def test_magic_detection() -> None:
    assert has_pdf_magic(b"%PDF-1.7\n...")
    assert has_pdf_magic(b"\n  %PDF-1.4")
    assert not has_pdf_magic(b"PK\x03\x04")


def test_extracts_reference_section_only() -> None:
    data = single_column(
        [BODY, ["Conclusion text here.", "References", "[1] A. Smith. First title. 2019.",
                "[2] B. Jones. Second title. 2020.", "Appendix A", "Proof details."]]
    )  # fmt: skip
    assert _texts(data) == ["[1] A. Smith. First title. 2019.", "[2] B. Jones. Second title. 2020."]


def test_two_column_page_is_read_column_by_column() -> None:
    left = ["Left column body text"] * 3 + [
        "References",
        "[1] A. Smith. Left col-",
        "umn title. 2019.",
    ]
    right = ["[2] B. Jones. Right column", "title. 2020.", "[3] C. Rao. Third. 2021."]
    lines = _texts(two_column_interleaved(left, right))
    assert lines == [
        "[1] A. Smith. Left col-",
        "umn title. 2019.",
        "[2] B. Jones. Right column",
        "title. 2020.",
        "[3] C. Rao. Third. 2021.",
    ]


def test_running_headers_and_page_numbers_are_removed() -> None:
    pages = [BODY, BODY, ["References", "[1] A. Smith. Title one. 2019."],
             ["[2] B. Jones. Title two. 2020."]]  # fmt: skip
    data = single_column(pages, header="Journal of Testing, Vol. 12", page_numbers=True)
    assert _texts(data) == ["[1] A. Smith. Title one. 2019.", "[2] B. Jones. Title two. 2020."]


def test_remove_running_lines_keeps_unique_edge_lines() -> None:
    pages = [["Header", "unique a", "3"], ["Header", "unique b", "Page 4 of 9"]]
    assert remove_running_lines(pages) == [["unique a"], ["unique b"]]


def test_scanned_pdf_gives_friendly_error() -> None:
    with pytest.raises(ScannedPdfError, match="scanned image"):
        pdf_text_pages(image_only())


def test_missing_reference_heading() -> None:
    with pytest.raises(InputError, match="No References"):
        pdf_lines(single_column([BODY]))


def test_not_a_pdf() -> None:
    with pytest.raises(InputError, match="not a PDF"):
        pdf_lines(b"just some text")


def test_damaged_pdf() -> None:
    with pytest.raises(InputError, match="could not be read"):
        pdf_lines(b"%PDF-1.4\n%garbage that is not a pdf body")


def test_password_protected_pdf() -> None:
    data = build_pdf([[(72, 700, "secret")]], password="hunter22")
    with pytest.raises(InputError, match="password-protected"):
        pdf_lines(data)


def test_page_limit() -> None:
    data = single_column([BODY, BODY, BODY])
    with pytest.raises(InputError, match="limit is 2"):
        pdf_text_pages(data, IngestConfig(max_pdf_pages=2))


def test_blank_page_between_text_pages_is_tolerated() -> None:
    data = single_column([BODY, [], ["References", "[1] A. Smith. Title one. 2019."]])
    assert _texts(data) == ["[1] A. Smith. Title one. 2019."]


def test_fragments_on_one_baseline_form_one_line() -> None:
    data = build_pdf([[*((72, 700 - i * 13, line) for i, line in enumerate(BODY)),
                       (72, 500, "References"), (72, 480, "[1] A. Smith,"),
                       (140, 480, "Title one. 2019.")]])  # fmt: skip
    assert _texts(data) == ["[1] A. Smith, Title one. 2019."]
