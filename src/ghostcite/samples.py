"""Locate the bundled sample documents and the demo response bundle.

Wheels ship the repository's ``samples/`` folder as ``ghostcite/_samples`` (see
``pyproject.toml``). An editable or source checkout uses ``samples/`` at the repository
root directly.
"""

from __future__ import annotations

from pathlib import Path

from ghostcite.errors import InputError

SAMPLE_BIB = "sample.bib"
SAMPLE_TEXT = "sample.txt"
SAMPLE_PDF = "sample.pdf"
DEMO_BUNDLE = Path("demo_cache") / "bundle.json"


def samples_dir() -> Path:
    """Directory holding the sample files, installed or in a source checkout."""
    packaged = Path(__file__).resolve().parent / "_samples"
    if packaged.is_dir():
        return packaged
    checkout = Path(__file__).resolve().parents[2] / "samples"
    if checkout.is_dir():
        return checkout
    raise InputError("The GhostCite sample files are not installed.")


def sample_path(name: str | Path) -> Path:
    """Path of one sample file, with a clear error if it is missing."""
    path = samples_dir() / name
    if not path.is_file():
        raise InputError(f"Sample file {Path(name).as_posix()} was not found.")
    return path
