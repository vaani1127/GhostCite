"""End-to-end CLI tests: every output format and every documented exit code."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from ghostcite import cli, service
from ghostcite.errors import SearchServiceError
from ghostcite.search.backends import DEMO_BUNDLE_FORMAT
from ghostcite.settings import API_KEY_ENV
from tests.helpers import (
    ATTENTION,
    BOOK,
    FABRICATED,
    WRONG_YEAR,
    FixtureTransport,
    numbered,
    recorded_responses,
)

runner = CliRunner()


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> FixtureTransport:
    """Pretend a key is configured and route live searches to recorded fixtures."""
    fake = FixtureTransport()
    monkeypatch.setenv(API_KEY_ENV, "test-key-not-real")
    monkeypatch.setattr(service, "LiveTransport", lambda api_key, timeout: fake)
    return fake


@pytest.fixture
def refs(tmp_path: Path) -> Path:
    path = tmp_path / "refs.txt"
    path.write_text(numbered(ATTENTION, WRONG_YEAR, FABRICATED, BOOK), encoding="utf-8")
    return path


def test_table_output(transport: FixtureTransport, refs: Path) -> None:
    result = runner.invoke(cli.app, ["check", str(refs)])
    assert result.exit_code == 0, result.output
    assert "Verified" in result.output
    assert "Not found" in result.output
    assert "Integrity score 62.5 / 100" in result.output
    assert transport.account_calls == 1


def test_json_to_stdout(transport: FixtureTransport, refs: Path) -> None:
    result = runner.invoke(cli.app, ["check", str(refs), "--format", "json", "--quiet"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [r["verdict"] for r in payload["results"]] == [
        "VERIFIED",
        "METADATA_MISMATCH",
        "NOT_FOUND",
        "VERIFIED",
    ]
    assert payload["source_name"] == "refs.txt"


@pytest.mark.parametrize(
    ("name", "marker"),
    [
        ("report.md", "# GhostCite report"),
        ("report.html", "<!doctype html>"),
        ("report.sarif", '"version": "2.1.0"'),
        ("report.json", '"results"'),
    ],
)  # fmt: skip
def test_output_file_format_is_inferred(
    transport: FixtureTransport, refs: Path, tmp_path: Path, name: str, marker: str
) -> None:
    target = tmp_path / name
    result = runner.invoke(cli.app, ["check", str(refs), "--output", str(target)])
    assert result.exit_code == 0, result.output
    assert marker in target.read_text(encoding="utf-8")
    assert "Report written to" in result.output


def test_sarif_uri_option(transport: FixtureTransport, refs: Path) -> None:
    result = runner.invoke(
        cli.app, ["check", str(refs), "-f", "sarif", "-q", "--sarif-uri", "docs/refs.bib"]
    )
    log = json.loads(result.stdout)
    uris = {
        r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for r in log["runs"][0]["results"]
    }
    assert uris == {"docs/refs.bib"}


def test_unknown_output_suffix_is_a_usage_error(
    transport: FixtureTransport, refs: Path, tmp_path: Path
) -> None:
    result = runner.invoke(cli.app, ["check", str(refs), "--output", str(tmp_path / "report.xyz")])
    assert result.exit_code == 2
    assert "Cannot tell the format" in result.output


@pytest.mark.parametrize(("threshold", "code"), [("1", 1), ("2", 1), ("3", 0)])
def test_fail_on_threshold(
    transport: FixtureTransport, refs: Path, threshold: str, code: int
) -> None:
    # The fixture document has one NOT_FOUND and one METADATA_MISMATCH.
    result = runner.invoke(cli.app, ["check", str(refs), "--fail-on", threshold, "-q"])
    assert result.exit_code == code


def test_stdin_input(transport: FixtureTransport) -> None:
    result = runner.invoke(cli.app, ["check", "-", "-f", "json", "-q"], input=numbered(ATTENTION))
    assert result.exit_code == 0
    assert json.loads(result.stdout)["results"][0]["verdict"] == "VERIFIED"


def test_missing_key_points_to_demo(refs: Path) -> None:
    result = runner.invoke(cli.app, ["check", str(refs)])
    assert result.exit_code == 2
    assert "--demo" in result.output


def test_service_errors_exit_with_code_3(
    monkeypatch: pytest.MonkeyPatch, transport: FixtureTransport, refs: Path
) -> None:
    def reject(params: object) -> dict[str, object]:
        raise SearchServiceError("SerpApi rejected the API key (HTTP 401).")

    monkeypatch.setattr(transport, "search", reject)
    result = runner.invoke(cli.app, ["check", str(refs)])
    assert result.exit_code == 3
    assert "rejected the API key" in result.output


def test_insufficient_credits_exit_with_code_3(transport: FixtureTransport, refs: Path) -> None:
    transport.searches_left = 0
    result = runner.invoke(cli.app, ["check", str(refs)])
    assert result.exit_code == 3
    assert "searches" in result.output
    assert transport.calls == []


def test_offline_run_after_a_live_run(transport: FixtureTransport, refs: Path) -> None:
    runner.invoke(cli.app, ["check", str(refs), "-q"])
    result = runner.invoke(cli.app, ["check", str(refs), "--offline", "-f", "json", "-q"])
    payload = json.loads(result.stdout)
    assert payload["mode"] == "offline"
    assert payload["summary"]["credits_used"] == 0


def test_demo_without_a_file_uses_the_bundled_sample(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sample = tmp_path / "sample.bib"
    sample.write_text(
        "@inproceedings{vaswani2017, title={Attention is all you need}, "
        "author={Vaswani, Ashish and Shazeer, Noam}, booktitle={NeurIPS}, year={2017}}\n",
        encoding="utf-8",
    )
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps({"format": DEMO_BUNDLE_FORMAT, "responses": recorded_responses()}), "utf-8"
    )
    monkeypatch.setattr(cli, "sample_path", lambda name: sample)
    monkeypatch.setattr(service, "sample_path", lambda name: bundle)
    result = runner.invoke(cli.app, ["check", "--demo", "-f", "json", "-q"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["mode"] == "demo"
    assert payload["results"][0]["verdict"] == "VERIFIED"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["check"], "use --demo"),
        (["check", "--offline", "--demo"], "cannot be combined"),
        (["check", "missing.txt"], "File not found"),
    ],
)
def test_usage_errors(args: list[str], message: str) -> None:
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 2
    assert message in result.output


def test_oversized_file(tmp_path: Path) -> None:
    big = tmp_path / "big.txt"
    with big.open("wb") as handle:
        handle.truncate(10 * 1024 * 1024 + 1)
    result = runner.invoke(cli.app, ["check", str(big)])
    assert result.exit_code == 2
    assert "larger than" in result.output


def test_wrong_file_type(tmp_path: Path) -> None:
    fake_pdf = tmp_path / "paper.pdf"
    fake_pdf.write_bytes(b"this is not a pdf")
    result = runner.invoke(cli.app, ["check", str(fake_pdf)])
    assert result.exit_code == 2
    assert "not a PDF" in result.output


def test_cache_commands(transport: FixtureTransport, refs: Path) -> None:
    runner.invoke(cli.app, ["check", str(refs), "-q"])
    stats = runner.invoke(cli.app, ["cache", "stats"])
    assert stats.exit_code == 0
    assert "Responses:" in stats.output
    assert "(0 expired)" in stats.output

    aborted = runner.invoke(cli.app, ["cache", "clear"], input="n\n")
    assert aborted.exit_code == 1
    cleared = runner.invoke(cli.app, ["cache", "clear", "--yes"])
    assert cleared.exit_code == 0
    assert "Removed 6 cached responses." in cleared.output


def test_verbose_flag_is_accepted(transport: FixtureTransport, refs: Path) -> None:
    result = runner.invoke(cli.app, ["-vv", "check", str(refs), "-q", "-f", "json"])
    assert result.exit_code == 0


def test_progress_bar_on_a_terminal(
    monkeypatch: pytest.MonkeyPatch, transport: FixtureTransport, refs: Path
) -> None:
    captured = StringIO()
    monkeypatch.setattr(
        cli, "_stderr", lambda: Console(file=captured, force_terminal=True, width=100)
    )

    result = runner.invoke(cli.app, ["check", str(refs), "-f", "json"])
    assert result.exit_code == 0
    assert "Checking references" in captured.getvalue()


def test_web_command_binds_to_localhost_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    seen: dict[str, object] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: seen.update(kwargs))
    result = runner.invoke(cli.app, ["web"])
    assert result.exit_code == 0
    assert seen["host"] == "127.0.0.1"
    assert seen["port"] == 8000
    assert "warning" not in result.output


@pytest.mark.parametrize(
    ("host", "warns"),
    [
        ("0.0.0.0", True),  # noqa: S104 - the warning for this bind address is under test
        ("192.168.1.5", True),
        ("localhost", False),
        ("::1", False),
    ],
)
def test_web_command_warns_on_non_loopback(
    monkeypatch: pytest.MonkeyPatch, host: str, warns: bool
) -> None:
    import uvicorn

    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: None)
    result = runner.invoke(cli.app, ["web", "--host", host, "--port", "9000"])
    assert result.exit_code == 0
    output = " ".join(result.output.split())  # rich wraps long lines
    assert ("reachable from other machines" in output) is warns
