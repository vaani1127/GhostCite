from __future__ import annotations

import runpy
import sys

import pytest
from typer.testing import CliRunner

from ghostcite import __version__
from ghostcite.cli import app


def test_version_flag() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"ghostcite {__version__}"


def test_python_dash_m_entry_point(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["ghostcite", "--version"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("ghostcite", run_name="__main__")
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out
