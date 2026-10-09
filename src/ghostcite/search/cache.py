"""Persistent SQLite cache of SerpApi responses.

Every search costs a credit, while checking the same paper twice should not. Responses
are stored under a hash of the normalized request parameters, which never include the
API key. The cache lives in the user's cache directory (see ``Settings.cache_dir``),
never inside the repository.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self

CACHE_FILE_NAME = "search-cache.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    key     TEXT PRIMARY KEY,
    engine  TEXT NOT NULL,
    query   TEXT NOT NULL,
    created REAL NOT NULL,
    body    TEXT NOT NULL
)
"""


def cache_key(params: Mapping[str, str]) -> str:
    """Stable key for a request: SHA-256 of its parameters, sorted, without ``api_key``."""
    canonical = json.dumps(
        {key: str(value) for key, value in params.items() if key != "api_key"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CacheStats:
    """Summary shown by ``ghostcite cache stats``."""

    path: Path
    entries: int
    expired: int
    size_bytes: int


class SqliteCache:
    """Thread-safe response cache with a time-to-live.

    One connection is shared behind a lock. SQLite serializes writes anyway, and the
    lock keeps the connection safe to use from the pipeline's worker threads.
    """

    def __init__(
        self,
        directory: Path,
        ttl_seconds: float,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / CACHE_FILE_NAME
        self._ttl = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        with self._lock, self._db:
            self._db.execute(_SCHEMA)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            self._db.close()

    def _fresh_since(self) -> float:
        return self._clock() - self._ttl

    def get(self, params: Mapping[str, str]) -> dict[str, Any] | None:
        """Return the cached response for ``params``, or ``None`` if absent or expired."""
        with self._lock:
            row = self._db.execute(
                "SELECT body FROM responses WHERE key = ? AND created >= ?",
                (cache_key(params), self._fresh_since()),
            ).fetchone()
        if row is None:
            return None
        body: dict[str, Any] = json.loads(row[0])
        return body

    def contains(self, params: Mapping[str, str]) -> bool:
        """True when a fresh response for ``params`` is cached."""
        return self.get(params) is not None

    def put(self, params: Mapping[str, str], response: Mapping[str, Any]) -> None:
        """Store ``response`` for ``params``, replacing any older entry."""
        row = (
            cache_key(params),
            params.get("engine", ""),
            params.get("q", ""),
            self._clock(),
            json.dumps(response, ensure_ascii=False, separators=(",", ":")),
        )
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?)", row)

    def export(self, keys: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Return fresh responses for the given cache keys (used to build the demo bundle)."""
        wanted = list(dict.fromkeys(keys))
        found: dict[str, dict[str, Any]] = {}
        with self._lock:
            for key in wanted:
                row = self._db.execute(
                    "SELECT body FROM responses WHERE key = ? AND created >= ?",
                    (key, self._fresh_since()),
                ).fetchone()
                if row is not None:
                    found[key] = json.loads(row[0])
        return found

    def stats(self) -> CacheStats:
        """Count entries and expired entries, and report the file size."""
        with self._lock:
            total = self._db.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
            expired = self._db.execute(
                "SELECT COUNT(*) FROM responses WHERE created < ?", (self._fresh_since(),)
            ).fetchone()[0]
        return CacheStats(self.path, int(total), int(expired), self.path.stat().st_size)

    def clear(self) -> int:
        """Delete every cached response and return how many were removed."""
        with self._lock, self._db:
            removed = self._db.execute("DELETE FROM responses").rowcount
        with self._lock:
            self._db.execute("VACUUM")
        return int(removed)
