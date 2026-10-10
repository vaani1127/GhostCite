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

from ghostcite.errors import InputError
from ghostcite.redact import register_secret

API_KEY_ENV = "SERPAPI_API_KEY"
CACHE_DIR_ENV = "GHOSTCITE_CACHE_DIR"
CREDITS_LOG_ENV = "GHOSTCITE_CREDITS_LOG"
CREDITS_LOG_NAME = "credits.log"
HOSTED_DEMO_ENV = "GHOSTCITE_HOSTED_DEMO"
_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})


@dataclass(frozen=True, slots=True)
class Settings:
    """Machine-specific settings for one GhostCite process."""

    api_key: SecretStr | None
    cache_dir: Path
    credits_log: Path | None = None
    """Where live runs record their search usage (see :mod:`ghostcite.credits`); ``None``
    disables the log."""
    hosted_demo: bool = False
    """A public, demo-only deployment: the web UI refuses every live check, even when a
    key happens to be configured (``GHOSTCITE_HOSTED_DEMO=true``)."""

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
    raw_cache = merged.get(CACHE_DIR_ENV, "").strip()
    cache_dir = Path(raw_cache) if raw_cache else Path(user_cache_dir("ghostcite", False))
    return Settings(
        api_key=SecretStr(raw_key) if raw_key else None,
        cache_dir=cache_dir,
        credits_log=_credits_log(merged.get(CREDITS_LOG_ENV, "").strip(), cache_dir),
        hosted_demo=_flag(HOSTED_DEMO_ENV, merged.get(HOSTED_DEMO_ENV, "")),
    )


def _flag(name: str, raw: str) -> bool:
    """Parse a true/false setting; an unrecognised value is an error, never a guess."""
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise InputError(f"{name} must be true or false.")


def _credits_log(configured: str, cache_dir: Path) -> Path:
    """Where live runs log their search usage.

    ``GHOSTCITE_CREDITS_LOG`` if set; else ``.dev/credits.log`` when the working directory
    has a ``.dev`` folder (a development checkout, where the folder is gitignored); else
    ``credits.log`` next to the cache.
    """
    if configured:
        return Path(configured)
    dev = Path.cwd() / ".dev"
    if dev.is_dir():
        return dev / CREDITS_LOG_NAME
    return cache_dir / CREDITS_LOG_NAME
