"""Run the GhostCite evaluation.

Usage::

    python eval/run.py                              # replay eval/responses.json: free, no key
    python eval/run.py --live --split tuning        # fill the local cache for the tuning split
    python eval/run.py --live --split test          # then the held-out test split, once
    python eval/run.py --record                     # save the cached responses for replay

Each validated row is checked twice: as a raw reference string in a fixed, mixed citation
style (the parser is evaluated end to end), and as a BibTeX entry. Live runs refuse to
start when the account would keep fewer than ``--reserve`` searches, and every live run
is logged to ``.dev/credits.log``. Results go to ``eval/results.json`` and
``eval/results.md``.

``eval/responses.json`` holds every response the evaluation used (trimmed and
sanitized), so the default replay reproduces all numbers on any machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ghostcite.config import SEARCH
from ghostcite.document import Document, load_document, load_text
from ghostcite.evaluation.dataset import EvalRow, load_dataset
from ghostcite.evaluation.metrics import Outcome, summarize
from ghostcite.evaluation.report import to_markdown
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
REPLAY = EVAL / "responses.json"
INPUTS = ("text", "bibtex")


def validated_rows() -> tuple[list[EvalRow], list[str]]:
    """Rows that passed eval/validate_dataset.py, and the ids that did not."""
    rows = load_dataset(EVAL / "dataset.jsonl")
    validation = json.loads((EVAL / "dataset_validation.json").read_text(encoding="utf-8"))
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


def log_credits(line: str) -> None:
    CREDITS_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    with CREDITS_LOG.open("a", encoding="utf-8") as log:
        log.write(f"{stamp} | {line}\n")


def preflight(
    document: Document, settings: Settings, max_searches: int, reserve: int, label: str
) -> int:
    """Estimate the cost and refuse a run that would break the account reserve."""
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
    worst_case = min(max_searches, len(planned))
    estimate = estimate_searches(uncached, max_searches)
    quota = fetch_quota(LiveTransport(settings.api_key, SEARCH.timeout_seconds))
    print(
        f"{label}: {uncached} uncached references, estimate {estimate} searches "
        f"(worst case {worst_case}); account has {quota.searches_left} left."
    )
    if quota.searches_left - worst_case < reserve:
        raise SystemExit(
            f"Refusing to run: the worst case would leave fewer than {reserve} searches "
            "on the account. Ask before spending them."
        )
    log_credits(
        f"PRE-RUN estimate: eval {label} | estimated={estimate} | worst_case={worst_case} "
        f"| account_left_before={quota.searches_left}"
    )
    return quota.searches_left


def run_one(
    document: Document,
    settings: Settings,
    args: argparse.Namespace,
    recorder: RecordingStore | None,
) -> Report:
    """Check one document live, from the local cache (optionally recording), or by replay."""
    if args.live:
        options = RunOptions(mode=RunMode.LIVE, max_searches=args.max_searches)
        return run_check(document, settings, options)
    if recorder is not None:
        client = SearchClient(recorder, None, SearchBudget(0))
        return check_document(document, client, mode=RunMode.OFFLINE)
    if args.cache:
        return run_check(document, settings, RunOptions(mode=RunMode.OFFLINE))
    return run_check(document, settings, RunOptions(mode=RunMode.DEMO, demo_bundle=REPLAY))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--split", choices=["tuning", "test", "all"], default="all")
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
        "--record", action="store_true", help="write eval/responses.json from the local cache"
    )
    args = parser.parse_args(argv)
    if not (args.live or args.cache or args.record) and not REPLAY.is_file():
        raise SystemExit("eval/responses.json is missing; run with --cache or --live first.")

    rows, dropped = validated_rows()
    assignment = split_rows(rows)
    splits = [Split(args.split)] if args.split != "all" else [Split.TEST, Split.TUNING]
    inputs = INPUTS if args.input == "all" else (args.input,)
    settings = load_settings(dotenv_path=ROOT / ".env")
    mode_label = "live" if args.live else "cache" if args.cache or args.record else "replay"
    cache = SqliteCache(settings.cache_dir, SEARCH.cache_ttl_days * 86_400) if args.record else None
    recorder = RecordingStore(cache) if cache is not None else None

    results_path = EVAL / "results.json"
    results: dict[str, Any] = (
        json.loads(results_path.read_text(encoding="utf-8"))
        if results_path.is_file()
        else {"runs": {}}
    )
    results.update(
        {"seed": DEFAULT_SEED, "dataset": {"validated": len(rows), "dropped": len(dropped)}}
    )
    for split in splits:
        part = sorted((r for r in rows if assignment[r.id] is split), key=lambda r: r.id)
        for input_format in inputs:
            label = f"{split.value}/{input_format}"
            document, by_index = build_document(part, input_format)
            before = None
            if args.live:
                before = preflight(document, settings, args.max_searches, args.reserve, label)
            report = run_one(document, settings, args, recorder)
            if args.live:
                log_credits(
                    f"eval {label} | actual={report.summary.credits_used} "
                    f"| account_left_before={before}"
                )
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
    results_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (EVAL / "results.md").write_text(to_markdown(results), encoding="utf-8")
    if recorder is not None and cache is not None:
        payload = bundle_payload(recorder.entries(), datetime.now(tz=UTC).strftime("%Y-%m-%d"))
        REPLAY.write_text(
            json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        cache.close()
        print(f"Recorded {len(payload['entries'])} responses to {REPLAY.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
