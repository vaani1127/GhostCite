"""Runtime settings that come from the environment, such as the API key and cache location.

Tunable algorithm parameters live in :mod:`ghostcite.config`. This module only resolves
values that differ between machines. The API key is wrapped in :class:`SecretStr` (whose
``repr`` is masked) and registered for redaction as soon as it is loaded.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from platformdirs import user_cache_dir
from pydantic import SecretStr

from ghostcite.redact import register_secret

API_KEY_ENV = "SERPAPI_API_KEY"
CACHE_DIR_ENV = "GHOSTCITE_CACHE_DIR"


@dataclass(frozen=True, slots=True)
class Settings:
    """Machine-specific settings for one GhostCite process."""

    api_key: SecretStr | None
    cache_dir: Path

    @property
    def has_api_key(self) -> bool:
        """True when a non-empty SerpApi key is configured."""
        return self.api_key is not None


def load_settings(
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | None = None,
) -> Settings:
    """Resolve settings from ``environ`` (default: ``os.environ``) and a ``.env`` file.

    Real environment variables win over ``.env`` entries, following the usual convention.
    ``dotenv_path`` defaults to ``.env`` in the current directory. The file is read
    without modifying ``os.environ``.
    """
    env = dict(os.environ if environ is None else environ)
    dotenv_file = dotenv_path if dotenv_path is not None else Path.cwd() / ".env"
    file_values = (
        {k: v for k, v in dotenv_values(dotenv_file).items() if v is not None}
        if dotenv_file.is_file()
        else {}
    )
    merged = {**file_values, **env}

    raw_key = merged.get(API_KEY_ENV, "").strip()
    if raw_key:
        register_secret(raw_key)
    cache_dir = merged.get(CACHE_DIR_ENV, "").strip()
    return Settings(
        api_key=SecretStr(raw_key) if raw_key else None,
        cache_dir=Path(cache_dir) if cache_dir else Path(user_cache_dir("ghostcite", False)),
    )
