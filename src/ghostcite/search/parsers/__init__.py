"""Turn raw SerpApi responses into :class:`ghostcite.models.Candidate` objects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def as_dict(value: object) -> Mapping[str, Any]:
    """``value`` if it is a JSON object, else an empty mapping (responses are untrusted)."""
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    """``value`` if it is a JSON array, else an empty list."""
    return value if isinstance(value, list) else []


def as_str(value: object) -> str | None:
    """``value`` stripped if it is a non-empty string, else ``None``."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
