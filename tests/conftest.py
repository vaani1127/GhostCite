"""Shared test setup.

Outbound network access is blocked for the whole suite by ``--allow-hosts`` in
``pyproject.toml``; ``tests/unit/test_network_block.py`` proves the block works. The
autouse fixture below adds a second safety net: no test can see a real API key or the
developer's real cache, because the environment variables are removed and the working
directory (where ``.env`` would be read from) is a fresh temporary directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostcite.settings import API_KEY_ENV, CACHE_DIR_ENV

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.setenv(CACHE_DIR_ENV, str(tmp_path / "cache"))
    monkeypatch.chdir(tmp_path)
