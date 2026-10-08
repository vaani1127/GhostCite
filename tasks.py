"""Developer task runner that works the same on Windows and Linux (stdlib only).

Usage: ``python tasks.py <task>``. Run ``python tasks.py --help`` to list the tasks.
Every task runs tools through the current interpreter (``sys.executable -m …``), so
it always uses the active virtual environment, whatever the shell or OS.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Sequence

Step = Sequence[str]


def _run(*steps: Step) -> int:
    """Run each step in order and stop at the first failure, returning its exit code."""
    for step in steps:
        print(f"$ {' '.join(step)}", flush=True)
        code = subprocess.call([sys.executable, *step])
        if code != 0:
            return code
    return 0


LINT: list[Step] = [["-m", "ruff", "check", "."], ["-m", "ruff", "format", "--check", "."]]
TYPES: list[Step] = [["-m", "mypy"]]
TEST: list[Step] = [["-m", "pytest"]]

TASKS: dict[str, tuple[str, Callable[[], int]]] = {
    "install": (
        "Install GhostCite in editable mode with dev tools and git hooks",
        lambda: _run(
            ["-m", "pip", "install", "-e", ".[dev]"],
            ["-m", "pre_commit", "install"],
        ),
    ),
    "fmt": (
        "Auto-format and auto-fix lint issues",
        lambda: _run(["-m", "ruff", "format", "."], ["-m", "ruff", "check", "--fix", "."]),
    ),
    "lint": ("ruff check + ruff format --check", lambda: _run(*LINT)),
    "types": ("mypy --strict", lambda: _run(*TYPES)),
    "test": ("pytest with coverage (fails under 90%)", lambda: _run(*TEST)),
    "check": ("All quality gates: lint, types, tests", lambda: _run(*LINT, *TYPES, *TEST)),
    "eval": ("Run the evaluation on cached data (no credits)", lambda: _run(["eval/run.py"])),
    "web": ("Start the local web UI", lambda: _run(["-m", "ghostcite", "web"])),
}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the task name and run it."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "task",
        choices=sorted(TASKS),
        help="; ".join(f"{name}: {desc}" for name, (desc, _) in sorted(TASKS.items())),
    )
    args = parser.parse_args(argv)
    _, action = TASKS[args.task]
    return action()


if __name__ == "__main__":
    sys.exit(main())
