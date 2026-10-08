"""Scrub secrets from any text before it can reach a log, an exception or a report.

Redaction works in two layers. Exact secret values registered at runtime (the loaded
API key) are always replaced. As a backstop, anything shaped like a SerpApi key or an
``api_key=`` URL parameter is replaced too, which covers keys that were never
registered, e.g. keys embedded in URLs inside third-party exception messages.
"""

from __future__ import annotations

import re
import threading

REDACTED = "[REDACTED]"

# SerpApi private keys are 64-character hexadecimal strings.
_KEY_SHAPE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
# Matches the value of an api_key query parameter or key/value pair in URLs, JSON and repr.
_KEY_PARAM = re.compile(r"""(api_key["']?\s*[=:]\s*["']?)[^&\s"',}]+""", re.IGNORECASE)

_lock = threading.Lock()
_secrets: set[str] = set()

# Very short values would cause collateral redaction of ordinary words.
_MIN_SECRET_LENGTH = 8


def register_secret(value: str) -> None:
    """Remember ``value`` so that every later call to :func:`redact` removes it."""
    if len(value) >= _MIN_SECRET_LENGTH:
        with _lock:
            _secrets.add(value)


def redact(text: str) -> str:
    """Return ``text`` with registered secrets and key-shaped strings replaced."""
    with _lock:
        secrets = sorted(_secrets, key=len, reverse=True)
    for secret in secrets:
        text = text.replace(secret, REDACTED)
    text = _KEY_PARAM.sub(rf"\g<1>{REDACTED}", text)
    return _KEY_SHAPE.sub(REDACTED, text)
