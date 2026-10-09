from __future__ import annotations

import pytest

from ghostcite.config import IngestConfig
from ghostcite.document import (
    PASTED_TEXT_NAME,
    detect_format,
    load_document,
    load_text,
    safe_source_name,
)
from ghostcite.errors import InputError, ScannedPdfError
from ghostcite.models import SourceFormat
from tests.conftest import FIXTURES
from tests.pdf_factory import image_only, single_column

TEXT_REFS = (
    "[1] A. Vaswani, N. Shazeer, \u201cAttention is all you need,\u201d in NeurIPS, 2017.\n"
    "[2] K. He, X. Zhang, \u201cDeep residual learning for image recognition,\u201d "
    "in CVPR, 2016.\n"
)


@pytest.mark.parametrize(
    ("data", "filename", "expected"),
    [
        (b"%PDF-1.7 ...", "paper.pdf", SourceFormat.PDF),
        (b"%PDF-1.7 ...", "renamed.txt", SourceFormat.PDF),  # content wins over extension
        (b"@article{k, title={T}}", None, SourceFormat.BIBTEX),
        (b"  % comment\n@Book{k, title={T}}", "refs.txt", SourceFormat.BIBTEX),
        (b"just references", "refs.bib", SourceFormat.BIBTEX),
        (b"[1] A reference.", None, SourceFormat.TEXT),
        (b"Write to me at someone@example.org (2020).", None, SourceFormat.TEXT),
    ],
)
def test_detect_format(data: bytes, filename: str | None, expected: SourceFormat) -> None:
    assert detect_format(data, filename) is expected


@pytest.mark.parametrize(
    ("data", "filename", "message"),
    [
        (b"not really a pdf", "paper.pdf", "not a PDF document"),
        (b"PK\x03\x04 zipped content", "paper.docx", "not supported"),
        (b"\x89PNG\r\n\x1a\n\x00\x00", "figure.png", "not text"),
    ],
)
def test_wrong_file_types(data: bytes, filename: str, message: str) -> None:
    with pytest.raises(InputError, match=message):
        load_document(data, filename)


@pytest.mark.parametrize("data", [b"", b"   \n\t "])
def test_empty_input(data: bytes) -> None:
    with pytest.raises(InputError, match="empty"):
        load_document(data, "refs.txt")


def test_oversized_input() -> None:
    with pytest.raises(InputError, match="larger than the 1 MiB limit"):
        load_document(
            b"x" * (1024 * 1024 + 1), "big.txt", IngestConfig(max_input_bytes=1024 * 1024)
        )


def test_text_without_references() -> None:
    with pytest.raises(InputError, match="No references were found"):
        load_document(b"References\n\n", "notes.txt")


def test_too_many_references() -> None:
    text = "\n".join(f"[{i}] Author{i} A. Title number {i}. Venue, 2020." for i in range(1, 12))
    with pytest.raises(InputError, match="limit is 10"):
        load_text(text, IngestConfig(max_references=10))


def test_large_reference_list() -> None:
    text = "\n".join(
        f"[{i}] Sharma A{chr(65 + i % 26)}. Study number {i} of rural health. "
        "Indian J Med Res. 2019."
        for i in range(1, 221)
    )
    document = load_text(text)
    assert len(document.references) == 220
    assert document.references[-1].fields.title == "Study number 220 of rural health"


def test_pasted_text_document() -> None:
    document = load_text(TEXT_REFS)
    assert document.source_name == PASTED_TEXT_NAME
    assert document.source_format is SourceFormat.TEXT
    assert [r.fields.title for r in document.references] == [
        "Attention is all you need",
        "Deep residual learning for image recognition",
    ]
    assert [r.line for r in document.references] == [1, 2]


def test_duplicate_references_are_kept_for_the_pipeline_to_dedupe() -> None:
    document = load_text(TEXT_REFS + TEXT_REFS.replace("[1]", "[3]").replace("[2]", "[4]"))
    titles = [r.fields.title for r in document.references]
    assert titles.count("Attention is all you need") == 2


def test_unicode_text_document() -> None:
    document = load_text(
        "M\u00fcller, J. (2020). \u00dcber die Bedeutung von Daten. Z. Inform.\n"
        "\u00d1\u00fa\u00f1ez, P. (2019). Un estudio sobre la poblaci\u00f3n rural. Rev. Econ.\n"
    )
    assert [r.fields.authors[0].surname for r in document.references] == [
        "M\u00fcller",
        "\u00d1\u00fa\u00f1ez",
    ]


def test_bibtex_document_carries_warnings() -> None:
    data = (FIXTURES / "bib" / "mixed.bib").read_bytes()
    document = load_document(data, "C:\\Users\\someone\\thesis\\mixed.bib")
    assert document.source_name == "mixed.bib"
    assert document.source_format is SourceFormat.BIBTEX
    assert len(document.references) == 7
    assert len(document.warnings) == 3


def test_pdf_document() -> None:
    body = [f"Body sentence {i} with enough words to count as real text." for i in range(6)]
    references = [
        "References",
        "[1] A. Smith, \u201cA first study of things,\u201d 2019.",
        "[2] B. Jones, \u201cA second study of things,\u201d 2020.",
    ]
    data = single_column([body, references])
    document = load_document(data, "paper.pdf")
    assert document.source_format is SourceFormat.PDF
    assert [r.fields.title for r in document.references] == [
        "A first study of things",
        "A second study of things",
    ]
    assert all(r.line is None for r in document.references)


def test_scanned_pdf_document() -> None:
    with pytest.raises(ScannedPdfError):
        load_document(image_only(), "scan.pdf")


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (None, PASTED_TEXT_NAME),
        ("", PASTED_TEXT_NAME),
        ("/home/someone/papers/draft.pdf", "draft.pdf"),
        ("C:\\Users\\someone\\Desktop\\refs.bib", "refs.bib"),
        ("../../etc/passwd", "passwd"),
        ("x" * 300 + ".pdf", "x" * 120),
        ("folder/", "folder"),
    ],
)
def test_safe_source_name(filename: str | None, expected: str) -> None:
    assert safe_source_name(filename) == expected
