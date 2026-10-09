"""Build samples/demo_cache/bundle.json, the offline data behind ``ghostcite check --demo``.

Usage::

    python scripts/build_demo_bundle.py

Every sample in ``samples/`` is checked offline against the local search cache, and the
responses those checks read are collected. The bundle is written only if every reference
was answered, so the demo never shows SKIPPED. Each response is trimmed to the fields
GhostCite reads and sanitized again (older cache entries may predate stricter
sanitizing). No searches are spent.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from ghostcite.config import SEARCH
from ghostcite.document import load_document
from ghostcite.models import RunMode, Verdict
from ghostcite.pipeline import check_document
from ghostcite.samples import DEMO_BUNDLE, SAMPLE_BIB, SAMPLE_PDF, SAMPLE_TEXT
from ghostcite.search.backends import RecordingStore, bundle_payload
from ghostcite.search.budget import SearchBudget
from ghostcite.search.cache import SqliteCache
from ghostcite.search.client import SearchClient
from ghostcite.settings import load_settings

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def main() -> int:
    settings = load_settings()
    with SqliteCache(settings.cache_dir, SEARCH.cache_ttl_days * 86_400) as cache:
        store = RecordingStore(cache)
        for name in (SAMPLE_BIB, SAMPLE_TEXT, SAMPLE_PDF):
            path = SAMPLES / name
            if not path.is_file():
                print(f"skipping {name}: not present")
                continue
            document = load_document(path.read_bytes(), path.name)
            client = SearchClient(store, None, SearchBudget(0))
            report = check_document(document, client, mode=RunMode.OFFLINE)
            missing = [
                r.reference.index for r in report.results if r.verdict is Verdict.SKIPPED_BUDGET
            ]
            if missing:
                print(f"{name}: references {missing} have no cached results; run them live first.")
                return 1
            counts = {v.value: n for v, n in report.summary.counts.items() if n}
            print(f"{name}: {len(report.results)} references, {counts}")
    payload = bundle_payload(store.entries(), datetime.now(tz=UTC).strftime("%Y-%m-%d"))
    target = SAMPLES / DEMO_BUNDLE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload['entries'])} responses to {target.relative_to(SAMPLES.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
