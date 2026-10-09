"""Append-only log of live SerpApi usage, so every spent search can be accounted for.

Every live run, from the CLI, the web UI or the evaluation, appends one line: when it
ran, which surface ran it, how many searches it spent and how many the account had left
before. Lines never contain the API key or any query text. Logging problems are reported
as warnings and never fail a check.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def append_line(path: Path | None, line: str) -> None:
    """Append ``<UTC timestamp> | <line>`` to the log at ``path`` (no-op when ``None``)."""
    if path is None:
        return
    stamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as log:
            log.write(f"{stamp} | {line}\n")
    except OSError as exc:
        logger.warning("Could not write the credits log %s: %s", path, exc.strerror or exc)


def log_live_run(
    path: Path | None,
    *,
    surface: str,
    searches: int,
    references: int,
    account_left: int | None,
) -> None:
    """Record one finished (or failed) live run."""
    before = "not checked (all cached)" if account_left is None else str(account_left)
    append_line(
        path,
        f"live run ({surface}) | searches={searches} | references={references} "
        f"| account_left_before={before}",
    )
