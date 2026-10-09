"""Validate eval/dataset.jsonl against Crossref and arXiv (free APIs; no SerpApi credits).

Usage::

    python eval/validate_dataset.py

Writes ``eval/dataset_validation.json``. ``eval/run.py`` only evaluates rows marked ok.
Requests identify GhostCite with a plain User-Agent (no e-mail address) and are paced
politely.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

from ghostcite.evaluation.dataset import load_dataset
from ghostcite.evaluation.validate import to_json, validate_rows

ROOT = Path(__file__).resolve().parent
USER_AGENT = "GhostCite-eval/0.1 (+https://github.com/vaani1127/GhostCite)"
PAUSE_SECONDS = 0.5


def fetch(url: str) -> str:
    """GET ``url`` with a descriptive User-Agent, pausing between calls."""
    time.sleep(PAUSE_SECONDS)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - fixed https hosts
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        body: bytes = response.read()
    return body.decode("utf-8")


def main() -> int:
    rows = load_dataset(ROOT / "dataset.jsonl")
    results = validate_rows(rows, fetch)
    (ROOT / "dataset_validation.json").write_text(
        json.dumps(to_json(results), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    failed = {row_id: r for row_id, r in results.items() if not r.ok}
    print(f"{len(results) - len(failed)} of {len(results)} rows validated.")
    for row_id, result in sorted(failed.items()):
        print(f"  DROPPED {row_id}: {'; '.join(result.problems)}")
    for row_id, result in sorted(results.items()):
        if result.ok and result.notes:
            print(f"  note {row_id}: {'; '.join(result.notes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
