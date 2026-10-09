"""Fail if any committed fixture, sample or evaluation file could leak a credential,
an account link or personal data.

Every text file under ``eval/``, ``samples/`` and ``tests/fixtures/`` is scanned,
recursively. These folders hold recorded SerpApi, Crossref and arXiv responses, which is
where an API key, a link into the account's search archive or an e-mail address would
slip in.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRS = [ROOT / "eval", ROOT / "samples", ROOT / "tests" / "fixtures"]
TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".bib",
    ".txt",
    ".md",
    ".py",
    ".csv",
    ".yml",
    ".yaml",
    ".html",
    ".log",
}

_FORBIDDEN = {
    # A digest labelled "sha256:" (the frozen-dataset hash) is not a key.
    "64-hex key": re.compile(r"(?<![0-9a-fA-F])(?<!sha256:)[0-9a-fA-F]{64}(?![0-9a-fA-F])"),
    "api_key parameter": re.compile(r"api_key\s*[=:]\s*[\"']?(?!REDACTED)[^\s\"'&,}]{6,}", re.I),
    "e-mail address": re.compile(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"
    ),
    "archive link": re.compile(r"serpapi\.com/searches", re.I),
    "endpoint key": re.compile(r"\b(?:json_endpoint|markdown_endpoint|raw_html_file)\b"),
}


def _files() -> list[Path]:
    return sorted(
        path
        for directory in SCANNED_DIRS
        if directory.is_dir()
        for path in directory.rglob("*")
        if path.is_file() and path.suffix in TEXT_SUFFIXES and "__pycache__" not in path.parts
    )


def test_scanned_directories_exist() -> None:
    assert all(directory.is_dir() for directory in SCANNED_DIRS)
    assert len(_files()) > 20


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_no_secrets_or_personal_data(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    found = [name for name, pattern in _FORBIDDEN.items() if pattern.search(text)]
    assert not found, f"{path.relative_to(ROOT).as_posix()} contains: {', '.join(found)}"


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_line_endings_are_lf(path: Path) -> None:
    # Writers in eval/ and scripts/ use newline="\n", so files hash the same on every OS.
    assert b"\r\n" not in path.read_bytes()


@pytest.mark.parametrize("name", list(_FORBIDDEN))
def test_detectors_catch_their_pattern(name: str) -> None:
    samples = {
        "64-hex key": ["key " + "ab12" * 16],
        "api_key parameter": ["https://serpapi.com/search?api_key=abcdef123456"],  # gitleaks:allow
        "e-mail address": ["contact: someone.name+tag@example.co.in", "x@y.org"],
        "archive link": ["https://serpapi.com/searches/abc/def.json"],
        "endpoint key": ['{"json_endpoint": "x"}', '"markdown_endpoint": 1', "raw_html_file"],
    }
    for sample in samples[name]:
        assert _FORBIDDEN[name].search(sample), sample


def test_detectors_ignore_ordinary_text() -> None:
    clean = (
        'doi 10.1038/35002501 "title": "Attention is all you need" @article{vaswani2017, '
        + "sha256:"
        + "ab12" * 16
    )
    assert not [name for name, pattern in _FORBIDDEN.items() if pattern.search(clean)]
