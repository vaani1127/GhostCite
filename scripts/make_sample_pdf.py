"""Generate samples/sample.pdf, a short paper with real and fabricated references.

Usage::

    python scripts/make_sample_pdf.py

The references are read from ``samples/sample.txt``, so the PDF, the text sample and the
demo bundle always agree. ReportLab's invariant mode makes the output byte-for-byte
reproducible. Requires the ``dev`` extra (ReportLab is not a runtime dependency).
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

SAMPLES = Path(__file__).resolve().parents[1] / "samples"
TITLE = "Evidence Synthesis Methods Across Disciplines: A Short Review"
BODY = [
    "This short review is a sample document for GhostCite. It was written to look like a "
    "typical manuscript whose reference list was partly drafted with a language model. "
    "Some references below are real and correctly cited; others have a wrong year, a "
    "venue the paper never appeared in, a reworded title, replaced authors, or do not "
    "exist at all.",
    "Systematic reviews follow the PRISMA statement [2], and diagnostic studies often "
    "report ROC curves [3], [9]. Sequence models based on attention [1] and residual "
    "networks [7] dominate machine learning, while evolutionary search [4] remains "
    "popular in engineering. Decision making under risk [5], asset pricing [10] and "
    "theories of justice [6] are cited in economics. Clinical descriptions of new "
    "diseases [8] and new diagnostic panels [11] complete the list.",
]


def references() -> list[str]:
    """The numbered reference lines of samples/sample.txt."""
    lines = (SAMPLES / "sample.txt").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip().startswith("[")]


def build(target: Path) -> None:
    """Write the sample PDF to ``target``."""
    rl_config.invariant = True  # fixed timestamps and IDs: reproducible bytes
    styles = getSampleStyleSheet()
    reference_style = ParagraphStyle(
        "Reference", parent=styles["BodyText"], leftIndent=0.9 * cm, firstLineIndent=-0.9 * cm
    )
    story = [
        Paragraph(escape(TITLE), styles["Title"]),
        Paragraph("GhostCite sample document", styles["Italic"]),
        Spacer(1, 0.5 * cm),
        Paragraph("1. Introduction", styles["Heading2"]),
        *[Paragraph(escape(text), styles["BodyText"]) for text in BODY],
        Spacer(1, 0.3 * cm),
        Paragraph("References", styles["Heading2"]),
        *[Paragraph(escape(line), reference_style) for line in references()],
    ]
    document = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        title=TITLE,
        author="GhostCite sample",
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    document.build(story)


def main() -> int:
    target = SAMPLES / "sample.pdf"
    build(target)
    print(f"Wrote {target.relative_to(SAMPLES.parent)} with {len(references())} references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
