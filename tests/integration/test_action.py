"""The composite GitHub Action: static safety checks and a real run of its shell script."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
EXAMPLE = yaml.safe_load((ROOT / "docs" / "examples" / "ghostcite-workflow.yml").read_text("utf-8"))
STEPS: list[dict[str, Any]] = ACTION["runs"]["steps"]
CHECK = next(step for step in STEPS if step.get("id") == "check")


# ---------------------------------------------------------------- static checks


def test_action_is_composite_with_documented_inputs() -> None:
    assert ACTION["runs"]["using"] == "composite"
    assert ACTION["inputs"]["serpapi-api-key"]["required"] is True
    for name in ("files", "max-searches", "fail-on", "upload-sarif", "category", "python-version"):
        assert ACTION["inputs"][name]["required"] is False
        assert "description" in ACTION["inputs"][name]
    assert set(ACTION["outputs"]) == {"sarif-dir", "files", "failed"}


def test_inputs_never_interpolated_into_scripts() -> None:
    # Expression interpolation inside `run:` enables script injection and can print secrets.
    for step in STEPS:
        if "run" in step:
            assert "${{" not in step["run"], step["name"]


def test_api_key_only_travels_through_env() -> None:
    assert CHECK["env"]["SERPAPI_API_KEY"] == "${{ inputs.serpapi-api-key }}"
    text = (ROOT / "action.yml").read_text(encoding="utf-8")
    assert text.count("inputs.serpapi-api-key") == 1
    assert "SERPAPI_API_KEY" not in CHECK["run"]  # never echoed by the script


def test_third_party_actions_are_pinned_to_versions() -> None:
    uses = [step["uses"] for step in STEPS if "uses" in step]
    assert uses, "expected setup-python, cache and upload-sarif"
    for ref in uses:
        assert re.fullmatch(r"[\w-]+/[\w/-]+@v\d+", ref), ref


def test_sarif_is_uploaded_before_the_threshold_fails_the_job() -> None:
    names = [step["name"] for step in STEPS]
    assert names.index("Upload results to code scanning") < names.index(
        "Enforce the fail-on threshold"
    )
    upload = next(s for s in STEPS if s["name"] == "Upload results to code scanning")
    assert upload["if"].startswith("${{ always()")


def test_example_workflow_grants_code_scanning_permission() -> None:
    assert EXAMPLE["permissions"] == {"contents": "read", "security-events": "write"}
    step = EXAMPLE["jobs"]["ghostcite"]["steps"][1]
    assert step["with"]["serpapi-api-key"] == "${{ secrets.SERPAPI_API_KEY }}"


# ---------------------------------------------------------------- running the script


def _bash() -> str | None:
    """Git Bash on Windows (the bash.exe on PATH there is WSL's launcher), bash elsewhere."""
    if os.name == "nt":
        candidate = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Git/bin/bash.exe"
        return str(candidate) if candidate.is_file() else None
    return shutil.which("bash")


FAKE_GHOSTCITE = """#!/usr/bin/env bash
# Test double: log the call, write the requested output, exit like the real CLI would.
echo "$*" >> "$FAKE_LOG"
case "$*" in
  *--format\\ md*) echo "## report for $2"; exit 0 ;;
esac
out=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "--output" ]; then out="$arg"; fi
  prev="$arg"
done
[ -n "$out" ] && echo '{"version": "2.1.0"}' > "$out"
case "$2" in
  *bad*) exit 1 ;;
  *broken*) exit 3 ;;
esac
exit 0
"""


def _run_check_step(
    tmp_path: Path, files: dict[str, str], pattern: str, fail_on: str = ""
) -> tuple[int, dict[str, str], str, str]:
    bash = _bash()
    if bash is None:
        pytest.skip("bash is not available")
    workspace = tmp_path / "repo"
    for name, content in files.items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    workspace.mkdir(parents=True, exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    fake = bin_dir / "ghostcite"
    fake.write_text(FAKE_GHOSTCITE, encoding="utf-8", newline="\n")
    fake.chmod(0o755)
    output, summary, log = tmp_path / "output", tmp_path / "summary.md", tmp_path / "calls.log"
    for path in (output, summary, log):
        path.write_text("", encoding="utf-8")

    def posix(path: Path) -> str:
        return path.as_posix()

    def path_entry(path: Path) -> str:
        # PATH is colon-separated, so Git Bash needs "/c/..." rather than "C:/...".
        text = posix(path)
        if re.match(r"^[A-Za-z]:/", text):
            text = f"/{text[0].lower()}{text[2:]}"
        return text

    script = f'export PATH="{path_entry(bin_dir)}:$PATH"\n' + CHECK["run"]
    env = {
        **os.environ,
        "GITHUB_OUTPUT": posix(output),
        "GITHUB_STEP_SUMMARY": posix(summary),
        "GHOSTCITE_SARIF_DIR": posix(tmp_path / "sarif"),
        "INPUT_FILES": pattern,
        "INPUT_MAX_SEARCHES": "7",
        "INPUT_FAIL_ON": fail_on,
        "FAKE_LOG": posix(log),
        "SERPAPI_API_KEY": "not-a-real-key",
    }
    result = subprocess.run(  # noqa: S603 - fixed interpreter and test-controlled script
        [bash, "-c", script], cwd=workspace, env=env, capture_output=True, text=True, check=False
    )
    outputs = dict(
        line.split("=", 1)
        for line in output.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    return result.returncode, outputs, summary.read_text(encoding="utf-8"), log.read_text("utf-8")


def test_script_checks_every_matching_file(tmp_path: Path) -> None:
    files = {"refs.bib": "@misc{a}", "chapters/two/more.bib": "@misc{b}", "notes.txt": "x"}
    code, outputs, summary, log = _run_check_step(tmp_path, files, "**/*.bib")
    assert code == 0
    assert outputs["files"] == "2"
    assert outputs["failed"] == "false"
    sarifs = sorted(p.name for p in (tmp_path / "sarif").iterdir())
    assert sarifs == ["chapters_two_more.bib.sarif", "refs.bib.sarif"]
    assert "--sarif-uri chapters/two/more.bib" in log
    assert "--max-searches 7" in log
    assert "--fail-on" not in log
    assert summary.count("## report for") == 2
    assert "--offline --format md" in log  # the summary never spends credits
    assert "not-a-real-key" not in log


def test_script_reports_threshold_failures_without_failing_the_step(tmp_path: Path) -> None:
    code, outputs, _, log = _run_check_step(tmp_path, {"bad.bib": "", "good.bib": ""}, "*.bib", "1")
    assert code == 0  # the upload step still runs; a later step enforces the threshold
    assert outputs["failed"] == "true"
    assert "--fail-on 1" in log


def test_script_stops_on_service_errors(tmp_path: Path) -> None:
    code, _, _, _ = _run_check_step(tmp_path, {"broken.bib": ""}, "*.bib")
    assert code == 3


def test_script_with_no_matches_and_several_patterns(tmp_path: Path) -> None:
    code, outputs, _, _ = _run_check_step(
        tmp_path, {"a/x.bib": "", "b/y.bib": ""}, "a/*.bib b/*.bib"
    )
    assert (code, outputs["files"]) == (0, "2")
    code, outputs, _, _ = _run_check_step(tmp_path / "empty", {}, "**/*.bib")
    assert (code, outputs["files"]) == (0, "0")
