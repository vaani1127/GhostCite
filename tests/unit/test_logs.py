from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator

import pytest

from ghostcite.logs import LOGGER_NAME, JsonFormatter, configure_logging, get_logger
from ghostcite.redact import REDACTED, register_secret

_SECRET = "logsecret-0000-1111"


@pytest.fixture(autouse=True)
def _reset_package_logger() -> Iterator[None]:
    yield
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


def _record(msg: str, *args: object, **extra: object) -> logging.LogRecord:
    record = logging.makeLogRecord({"msg": msg, "args": args, "levelname": "INFO"})
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_get_logger_namespaces_under_package() -> None:
    assert get_logger("search").name == f"{LOGGER_NAME}.search"
    assert get_logger(f"{LOGGER_NAME}.cache").name == f"{LOGGER_NAME}.cache"
    assert get_logger(LOGGER_NAME).name == LOGGER_NAME


def test_human_logs_redact_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    register_secret(_SECRET)
    configure_logging("INFO")
    get_logger("test").info("calling with %s", _SECRET)
    err = capsys.readouterr().err
    assert _SECRET not in err
    assert REDACTED in err


def test_human_logs_redact_tracebacks(capsys: pytest.CaptureFixture[str]) -> None:
    register_secret(_SECRET)
    configure_logging("INFO")
    try:
        raise RuntimeError(f"bad key {_SECRET}")
    except RuntimeError:
        get_logger("test").exception("search failed")
    err = capsys.readouterr().err
    assert _SECRET not in err
    assert "RuntimeError" in err


def test_configure_logging_does_not_stack_handlers() -> None:
    configure_logging("INFO")
    configure_logging("DEBUG")
    logger = logging.getLogger(LOGGER_NAME)
    assert len(logger.handlers) == 1
    assert logger.level == logging.DEBUG


def test_json_formatter_emits_structured_fields() -> None:
    register_secret(_SECRET)
    line = JsonFormatter().format(_record("cache %s", "hit", engine="google_scholar", key=_SECRET))
    payload = json.loads(line)
    assert payload["message"] == "cache hit"
    assert payload["engine"] == "google_scholar"
    assert payload["key"] == REDACTED
    assert payload["level"] == "INFO"


def test_json_formatter_includes_redacted_exception() -> None:
    register_secret(_SECRET)
    try:
        raise ValueError(_SECRET)
    except ValueError:
        record = logging.makeLogRecord(
            {"msg": "x", "levelname": "ERROR", "exc_info": sys.exc_info()}
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError" in payload["exception"]
    assert _SECRET not in payload["exception"]


def test_configure_logging_json_mode(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json_format=True)
    get_logger("test").info("hello")
    assert json.loads(capsys.readouterr().err)["message"] == "hello"
