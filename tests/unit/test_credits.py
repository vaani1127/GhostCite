from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ghostcite.credits import append_line, log_live_run


def test_lines_are_timestamped_and_appended(tmp_path: Path) -> None:
    log = tmp_path / "a" / "credits.log"
    append_line(log, "first")
    log_live_run(log, surface="web", searches=3, references=4, account_left=120)
    lines = log.read_bytes().decode("utf-8").split("\n")
    assert lines[0].endswith(" UTC | first")
    assert lines[1].endswith(
        "| live run (web) | searches=3 | references=4 | account_left_before=120"
    )
    assert lines[2] == ""
    assert b"\r\n" not in log.read_bytes()


def test_no_path_means_no_log(tmp_path: Path) -> None:
    append_line(None, "ignored")
    assert list(tmp_path.iterdir()) == []


def test_write_errors_only_warn(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="ghostcite.credits"):
        append_line(blocker / "credits.log", "line")
    assert "Could not write the credits log" in caplog.text
