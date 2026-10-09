"""Run the GhostCite evaluation.

Usage::

    python eval/run.py                              # replay v1 from eval/responses.json: free
    python eval/run.py --dataset v2                 # replay v2 from eval/responses_v2.json: free
    python eval/run.py --live --split tuning        # v1: fill the local cache for the tuning split
    python eval/run.py --live --split test          # v1: then the held-out test split, once
    python eval/run.py --dataset v2 --live          # v2: the frozen held-out set, run once
    python eval/run.py --record                     # save the cached responses for replay

Each validated row is checked twice: as a raw reference string in a fixed, mixed citation
style (the parser is evaluated end to end), and as a BibTeX entry.

* **v1** (``eval/dataset.jsonl``) has a tuning split and a test split. Results go to
  ``eval/results.json`` and ``eval/results.md``.
* **v2** (``eval/dataset_v2.jsonl``) is entirely held out. It shares no paper with v1, was
  frozen (its SHA-256 is checked below) before any search, and was run once with the
  code frozen. Results go to ``eval/results_v2.json`` and ``eval/results_v2.md``.

Live runs refuse to start when the account would keep fewer than ``--reserve`` searches.
The estimate goes to ``.dev/credits.log`` before the run, and ``run_check`` logs the
searches actually used. ``eval/responses*.json`` hold every response the evaluation used
(trimmed and sanitized), so the default replay reproduces all numbers on any machine.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ghostcite.config import SEARCH
from ghostcite.credits import append_line
from ghostcite.document import Document, load_document, load_text
from ghostcite.evaluation.dataset import EvalRow, load_dataset
from ghostcite.evaluation.metrics import Outcome, summarize
from ghostcite.evaluation.report import HELD_OUT_V2_NOTE, POST_FIX_NOTE, to_markdown
from ghostcite.evaluation.split import DEFAULT_SEED, Split, split_rows
from ghostcite.evaluation.styles import assign_styles, render, to_bibtex
from ghostcite.models import Report, RunMode
from ghostcite.pipeline import check_document
from ghostcite.search.account import estimate_searches, fetch_quota
from ghostcite.search.backends import LiveTransport, RecordingStore, bundle_payload
from ghostcite.search.budget import SearchBudget
from ghostcite.search.cache import SqliteCache
from ghostcite.search.client import SearchClient
from ghostcite.search.planner import plan_queries
from ghostcite.service import RunOptions, run_check, uncached_references
from ghostcite.settings import Settings, load_settings

EVAL = Path(__file__).resolve().parent
ROOT = EVAL.parent
CREDITS_LOG = ROOT / ".dev" / "credits.log"
INPUTS = ("text", "bibtex")

V2_SHA256 = "sha256:e7e752544795eeabbd24b2a66f94ccbef04660b4bc341a6d6d22a83cf8888604"
"""SHA-256 of eval/dataset_v2.jsonl when it was frozen (also in docs/EVALUATION.md)."""


@dataclass(frozen=True, slots=True)
class Dataset:
    """Where one evaluation dataset and its outputs live."""

    name: str
    rows: Path
    validation: Path
    results: Path
    markdown: Path
    replay: Path
    split: bool
    """True when the rows are divided into tuning and test splits (v1)."""
    sha256: str | None = None
    note: str = POST_FIX_NOTE


DATASETS = {
    "v1": Dataset(
        "v1",
        EVAL / "dataset.jsonl",
        EVAL / "dataset_validation.json",
        EVAL / "results.json",
        EVAL / "results.md",
        EVAL / "responses.json",
        split=True,
    ),
    "v2": Dataset(
        "v2",
        EVAL / "dataset_v2.jsonl",
        EVAL / "dataset_v2_validation.json",
        EVAL / "results_v2.json",
        EVAL / "results_v2.md",
        EVAL / "responses_v2.json",
        split=False,
        sha256=V2_SHA256,
        note=HELD_OUT_V2_NOTE,
    ),
}


def sha256_of(path: Path) -> str:
    """``sha256:<hex>`` of a file's bytes (the prefix marks it as a digest, not a key)."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_lf(path: Path, text: str) -> None:
    """Write UTF-8 text with LF line endings on every platform."""
    path.write_text(text, encoding="utf-8", newline="\n")


def validated_rows(dataset: Dataset) -> tuple[list[EvalRow], list[str]]:
    """Rows that passed eval/validate_dataset.py, and the ids that did not."""
    if dataset.sha256 is not None and sha256_of(dataset.rows) != dataset.sha256:
        raise SystemExit(
            f"{dataset.rows.name} changed after it was frozen; a frozen held-out set must "
            "not be edited."
        )
    rows = load_dataset(dataset.rows)
    validation = json.loads(dataset.validation.read_text(encoding="utf-8"))
    keep = [row for row in rows if validation.get(row.id, {}).get("ok")]
    dropped = sorted(row.id for row in rows if row not in keep)
    return keep, dropped


def build_document(rows: list[EvalRow], input_format: str) -> tuple[Document, dict[int, EvalRow]]:
    """The rows as one document, and which reference index belongs to which row."""
    if input_format == "bibtex":
        document = load_document(to_bibtex(rows).encode("utf-8"), "evaluation.bib")
        by_id = {row.id: row for row in rows}
        return document, {ref.index: by_id[ref.key] for ref in document.references if ref.key}
    styles = assign_styles(rows, DEFAULT_SEED)
    text = "\n".join(f"[{i}] {render(row, styles[row.id])}" for i, row in enumerate(rows, 1))
    document = load_text(text)
    if len(document.references) != len(rows):
        raise SystemExit(
            f"The splitter found {len(document.references)} references for {len(rows)} rows; "
            "fix the reference splitter before evaluating."
        )
    return document, {ref.index: row for ref, row in zip(document.references, rows, strict=True)}


def outcomes_of(report: Report, rows_by_index: dict[int, EvalRow]) -> list[Outcome]:
    """Pair every result with its labelled row."""
    outcomes = []
    for result in report.results:
        best = result.best_match.candidate.title if result.best_match else None
        outcomes.append(
            Outcome(
                row=rows_by_index[result.reference.index],
                verdict=result.verdict,
                confidence=result.confidence,
                reason=result.reason,
                parsed_title=result.reference.fields.title,
                best_title=best,
            )
        )
    return outcomes


def preflight(
    document: Document, settings: Settings, max_searches: int, reserve: int, label: str
) -> None:
    """Print the estimate and refuse a run that would break the account reserve."""
    if settings.api_key is None:
        raise SystemExit("SERPAPI_API_KEY is not set. Add it to .env (see .env.example).")
    with SqliteCache(settings.cache_dir, SEARCH.cache_ttl_days * 86_400) as cache:
        uncached = uncached_references(document, cache)
        # Upper bound: every planned query that is not cached yet (follow-up strategies
        # run whenever a first answer is not conclusive).
        planned = {
            json.dumps(query.params, sort_keys=True)
            for reference in document.references
            for query in plan_queries(reference.fields)
            if not cache.contains(query.params)
        }
    # The uncapped planner estimate is what decides whether a dataset is small enough.
    estimate = estimate_searches(uncached, 10**6)
    worst_case = min(max_searches, len(planned))
    quota = fetch_quota(LiveTransport(settings.api_key, SEARCH.timeout_seconds))
    print(
        f"{label}: {uncached} uncached references, estimate {estimate} searches "
        f"(cap {max_searches}, worst case under the cap {worst_case}); "
        f"account has {quota.searches_left} left."
    )
    if estimate > max_searches:
        raise SystemExit(
            f"Refusing to run: the estimate ({estimate}) is above the cap ({max_searches}). "
            "Shrink the dataset; do not raise the cap."
        )
    if quota.searches_left - worst_case < reserve:
        raise SystemExit(
            f"Refusing to run: the worst case would leave fewer than {reserve} searches "
            "on the account. Ask before spending them."
        )
    append_line(
        CREDITS_LOG,
        f"PRE-RUN estimate: eval {label} | estimated={estimate} | cap={max_searches} "
        f"| worst_case={worst_case} | account_left_before={quota.searches_left}",
    )


def run_one(
    document: Document,
    settings: Settings,
    args: argparse.Namespace,
    dataset: Dataset,
    recorder: RecordingStore | None,
) -> Report:
    """Check one document live, from the local cache (optionally recording), or by replay."""
    if args.live:
        options = RunOptions(mode=RunMode.LIVE, max_searches=args.max_searches, surface="eval")
        return run_check(document, settings, options)
    if recorder is not None:
        client = SearchClient(recorder, None, SearchBudget(0))
        return check_document(document, client, mode=RunMode.OFFLINE)
    if args.cache:
        return run_check(document, settings, RunOptions(mode=RunMode.OFFLINE))
    return run_check(document, settings, RunOptions(mode=RunMode.DEMO, demo_bundle=dataset.replay))


def parts(dataset: Dataset, rows: list[EvalRow], split: str) -> list[tuple[str, list[EvalRow]]]:
    """(label prefix, rows) for each part of the dataset to run."""
    if not dataset.split:
        return [(dataset.name, sorted(rows, key=lambda r: r.id))]
    assignment = split_rows(rows)
    chosen = [Split(split)] if split != "all" else [Split.TEST, Split.TUNING]
    return [
        (s.value, sorted((r for r in rows if assignment[r.id] is s), key=lambda r: r.id))
        for s in chosen
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="v1")
    parser.add_argument("--split", choices=["tuning", "test", "all"], default="all", help="v1 only")
    parser.add_argument("--input", choices=[*INPUTS, "all"], default="all")
    parser.add_argument(
        "--live", action="store_true", help="spend SerpApi searches for cache misses"
    )
    parser.add_argument("--max-searches", type=int, default=100)
    parser.add_argument(
        "--reserve", type=int, default=80, help="searches that must stay on the account"
    )
    parser.add_argument("--cache", action="store_true", help="use the local cache, not the replay")
    parser.add_argument(
        "--record", action="store_true", help="write the replay file from the local cache"
    )
    args = parser.parse_args(argv)
    dataset = DATASETS[args.dataset]
    if not (args.live or args.cache or args.record) and not dataset.replay.is_file():
        raise SystemExit(f"{dataset.replay.name} is missing; run with --cache or --live first.")

    rows, dropped = validated_rows(dataset)
    inputs = INPUTS if args.input == "all" else (args.input,)
    settings = dataclasses.replace(
        load_settings(dotenv_path=ROOT / ".env"), credits_log=CREDITS_LOG
    )
    mode_label = "live" if args.live else "cache" if args.cache or args.record else "replay"
    cache = SqliteCache(settings.cache_dir, SEARCH.cache_ttl_days * 86_400) if args.record else None
    recorder = RecordingStore(cache) if cache is not None else None

    results: dict[str, Any] = (
        json.loads(dataset.results.read_text(encoding="utf-8"))
        if dataset.results.is_file()
        else {"runs": {}}
    )
    results.update(
        {
            "dataset_name": dataset.name,
            "seed": DEFAULT_SEED,
            "dataset": {"validated": len(rows), "dropped": len(dropped)},
        }
    )
    if dataset.sha256 is not None:
        results["dataset_sha256"] = dataset.sha256
    for prefix, part in parts(dataset, rows, args.split):
        for input_format in inputs:
            label = f"{prefix}/{input_format}"
            document, by_index = build_document(part, input_format)
            if args.live:
                preflight(document, settings, args.max_searches, args.reserve, label)
            report = run_one(document, settings, args, dataset, recorder)
            summary = summarize(outcomes_of(report, by_index))
            summary["credits_used"] = report.summary.credits_used
            summary["mode"] = mode_label
            results["runs"][label] = summary
            head = summary["headline"]
            print(
                f"{label}: false alarms {head['false_alarms']}/{head['real']}, "
                f"detected {head['detected']}/{head['fabricated']}, "
                f"unchecked {head['unchecked_real'] + head['unchecked_fabricated']}, "
                f"{report.summary.credits_used} live searches"
            )
    write_lf(dataset.results, json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    write_lf(dataset.markdown, to_markdown(results, dataset.note))
    if recorder is not None and cache is not None:
        payload = bundle_payload(recorder.entries(), datetime.now(tz=UTC).strftime("%Y-%m-%d"))
        write_lf(dataset.replay, json.dumps(payload, indent=1, ensure_ascii=False) + "\n")
        cache.close()
        print(f"Recorded {len(payload['entries'])} responses to {dataset.replay.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
