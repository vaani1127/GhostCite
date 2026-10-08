"""Logging setup with mandatory secret redaction.

Redaction happens in the formatter, on the fully rendered line (message, arguments and
traceback included), so no code path can bypass it by passing the key as a ``%s``
argument or inside an exception.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from ghostcite.redact import redact

LOGGER_NAME = "ghostcite"

# Attributes every LogRecord has. Anything else was passed through ``extra=`` and is
# emitted as a structured field.
_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class RedactingFormatter(logging.Formatter):
    """Human-readable formatter that redacts the final rendered line."""

    def format(self, record: logging.LogRecord) -> str:
        """Render the record, then strip anything secret-shaped from the result."""
        return redact(super().format(record))


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for machine-readable logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Render the record as JSON, including ``extra=`` fields, then redact it."""
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update({k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, default=str, ensure_ascii=False))


def get_logger(name: str) -> logging.Logger:
    """Return a child of the package logger, e.g. ``get_logger(__name__)``."""
    if name == LOGGER_NAME or name.startswith(LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def configure_logging(level: str = "WARNING", *, json_format: bool = False) -> None:
    """Attach a single redacting stderr handler to the package logger.

    Calling it again replaces the handler instead of stacking duplicates.
    """
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler()
    formatter: logging.Formatter = (
        JsonFormatter()
        if json_format
        else RedactingFormatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
