"""Build small PDFs on the fly for tests, so no binary fixtures live in the repository."""

from __future__ import annotations

import io
from collections.abc import Sequence

from reportlab.lib.pagesizes import A4
from reportlab.lib.pdfencrypt import StandardEncryption
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = A4
TOP = PAGE_HEIGHT - 80
LEADING = 13.0

Placement = tuple[float, float, str]


def build_pdf(pages: Sequence[Sequence[Placement]], *, password: str | None = None) -> bytes:
    """Draw each ``(x, y, text)`` placement in the given order, one list per page.

    Drawing order is preserved in the content stream, which lets tests reproduce PDFs
    whose stream order differs from the visual reading order.
    """
    buffer = io.BytesIO()
    encrypt = StandardEncryption(password, canPrint=1) if password else None
    pdf = canvas.Canvas(buffer, pagesize=A4, encrypt=encrypt)
    for placements in pages:
        pdf.setFont("Helvetica", 9)
        for x, y, text in placements:
            pdf.drawString(x, y, text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def single_column(
    pages: Sequence[Sequence[str]],
    *,
    header: str | None = None,
    page_numbers: bool = False,
) -> bytes:
    """One column of text per page, with an optional running header and page numbers."""
    rendered: list[list[Placement]] = []
    for number, lines in enumerate(pages, 1):
        placements: list[Placement] = []
        if header:
            placements.append((72, PAGE_HEIGHT - 40, header))
        placements.extend((72, TOP - i * LEADING, line) for i, line in enumerate(lines))
        if page_numbers:
            placements.append((PAGE_WIDTH / 2 - 5, 30, str(number)))
        rendered.append(placements)
    return build_pdf(rendered)


def two_column_interleaved(left: Sequence[str], right: Sequence[str]) -> bytes:
    """A two-column page whose content stream alternates left and right lines.

    Naive extraction of such a page interleaves the columns line by line.
    """
    placements: list[Placement] = []
    for i in range(max(len(left), len(right))):
        y = TOP - i * LEADING
        if i < len(left):
            placements.append((50, y, left[i]))
        if i < len(right):
            placements.append((PAGE_WIDTH / 2 + 15, y, right[i]))
    return build_pdf([placements])


def image_only() -> bytes:
    """A PDF with graphics but no text, like a scanned page."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for i in range(20):
        pdf.rect(50 + i * 5, 100 + i * 20, 400, 10, fill=1)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
