"""Fail if any committed fixture or sample could leak a credential or account link."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRS = [ROOT / "tests" / "fixtures", ROOT / "samples"]
SUFFIXES = {".json", ".bib", ".txt", ".md", ".jsonl"}

_FORBIDDEN = {
    "64-hex key": re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])"),
    "api_key parameter": re.compile(r"api_key\s*[=:]\s*[\"']?(?!REDACTED)[^\s\"'&,}]{6,}", re.I),
    "archive link": re.compile(r"serpapi\.com/searches/", re.I),
    "json_endpoint": re.compile(r"\"(?:json_endpoint|raw_html_file)\""),
}


def _files() -> list[Path]:
    return sorted(
        path
        for directory in SCANNED_DIRS
        if directory.is_dir()
        for path in directory.rglob("*")
        if path.suffix in SUFFIXES
    )


def test_fixture_directories_exist() -> None:
    assert (ROOT / "tests" / "fixtures").is_dir()


@pytest.mark.parametrize("path", _files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_secrets_in_fixtures(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    found = [name for name, pattern in _FORBIDDEN.items() if pattern.search(text)]
    assert not found, f"{path.name} contains: {', '.join(found)}"


@pytest.mark.parametrize("name", list(_FORBIDDEN))
def test_detectors_catch_their_pattern(name: str) -> None:
    samples = {
        "64-hex key": "key " + "ab12" * 16,
        "api_key parameter": "https://serpapi.com/search?api_key=abcdef123456",  # gitleaks:allow
        "archive link": "https://serpapi.com/searches/abc/def.json",
        "json_endpoint": '{"json_endpoint": "x"}',
    }
    assert _FORBIDDEN[name].search(samples[name])
