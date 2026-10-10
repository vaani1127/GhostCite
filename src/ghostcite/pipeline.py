"""Check every reference of a document: plan, search, match, decide.

References are checked in parallel with bounded concurrency. Identical references
(same title, first author and year) are searched once, and the duplicates reuse the
result. For each reference the planned queries run in order and stop as soon as a
candidate's title matches: the work is identified at that point, and more searches
could only cost credits.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime

from ghostcite import __version__
from ghostcite.config import MATCH, SEARCH, MatchConfig
from ghostcite.document import Document
from ghostcite.errors import BudgetExhaustedError
from ghostcite.match.normalize import fold, surname_key
from ghostcite.match.score import (
    agreement,
    best_match,
    match_candidate,
    title_status,
    versions_of,
)
from ghostcite.models import (
    Candidate,
    Engine,
    FieldStatus,
    MatchResult,
    Reference,
    ReferenceResult,
    Report,
    RunMode,
    SourceFormat,
    Summary,
    Verdict,
)
from ghostcite.search.client import ResponseSource, SearchClient
from ghostcite.search.parsers.google import parse_google
from ghostcite.search.parsers.scholar import parse_scholar
from ghostcite.search.planner import PlannedQuery, plan_queries
from ghostcite.verdict.rules import Decision, decide, integrity_score, unparseable

_BUDGET_REASON = "Not fully checked: the search budget for this run ran out first."
_OFFLINE_REASON = {
    RunMode.OFFLINE: "Not checked: no cached search result for this reference (offline mode).",
    RunMode.DEMO: "Not checked: this reference is not part of the bundled demo data.",
    RunMode.LIVE: "Not checked: no search result was available.",
}
DEMO_MISS_REASON = _OFFLINE_REASON[RunMode.DEMO]
"""Reason given to a reference that the demo bundle has no response for."""


@dataclass(frozen=True, slots=True)
class Progress:
    """Reported after each reference is checked."""

    done: int
    total: int
    result: ReferenceResult


ProgressCallback = Callable[[Progress], None]


def dedupe_key(reference: Reference) -> str:
    """References with the same key are the same citation, checked once.

    Every parsed field takes part. Two citations of one paper that differ in any field
    (venue, a co-author, year) are different citations, and each gets its own verdict.
    """
    fields = reference.fields
    if not fields.title:
        return "raw:" + fold(reference.raw)
    authors = ",".join(surname_key(a.surname) for a in fields.authors)
    parts = (fold(fields.title), authors, str(fields.year or ""), fold(fields.venue or ""))
    return "|".join((*parts, fields.doi or "", fields.entry_type or ""))


def _candidates(query: PlannedQuery, body: dict[str, object]) -> list[Candidate]:
    if query.engine is Engine.GOOGLE:
        return parse_google(body, query.text)
    return parse_scholar(body, query.text)


def _confident(best: MatchResult | None) -> bool:
    """A title match on which no field disagrees: no further search can improve on it.

    A title match that disagrees on a field is not final. Scholar often lists a work
    several times (preprint, journal, reprint), and the next strategy can surface the
    version the citation means, which avoids a false alarm.
    """
    return best is not None and title_status(best) is FieldStatus.MATCH and agreement(best)[0] == 0


class ReferenceChecker:
    """Runs the search plan for one reference at a time; safe to share between threads."""

    def __init__(self, client: SearchClient, mode: RunMode, cfg: MatchConfig = MATCH) -> None:
        self._client = client
        self._mode = mode
        self._cfg = cfg

    def check(self, reference: Reference) -> ReferenceResult:
        """Search, match and decide one reference."""
        fields = reference.fields
        if not fields.title:
            malformed = reference.source_format is SourceFormat.BIBTEX and fields.entry_type is None
            return _result(reference, unparseable(malformed_entry=malformed), None, (), 0)

        matches: list[MatchResult] = []
        queries: list[str] = []
        live = 0
        complete = True
        incomplete_reason = ""
        best: MatchResult | None = None
        for query in plan_queries(fields):
            try:
                response = self._client.search(query.params)
            except BudgetExhaustedError:
                complete, incomplete_reason = False, _BUDGET_REASON
                break
            queries.append(query.text)
            if response.source is ResponseSource.MISS or response.body is None:
                complete, incomplete_reason = False, _OFFLINE_REASON[self._mode]
                continue
            live += response.source is ResponseSource.LIVE
            matches.extend(
                match_candidate(fields, c, self._cfg) for c in _candidates(query, response.body)
            )
            best = best_match(matches, fields, self._cfg)
            if _confident(best):
                complete = True  # identity established; earlier misses no longer matter
                break

        decision = decide(
            fields,
            best,
            complete=complete,
            incomplete_reason=incomplete_reason,
            versions=versions_of(matches),
            match_cfg=self._cfg,
        )
        shown = (
            best
            if decision.verdict in (Verdict.VERIFIED, Verdict.METADATA_MISMATCH, Verdict.NOT_FOUND)
            else None
        )
        return _result(reference, decision, shown, tuple(queries), live)


def _result(
    reference: Reference,
    decision: Decision,
    best: MatchResult | None,
    queries: tuple[str, ...],
    live: int,
) -> ReferenceResult:
    return ReferenceResult(
        reference=reference,
        verdict=decision.verdict,
        confidence=decision.confidence,
        reason=decision.reason,
        best_match=best,
        mismatched_fields=decision.mismatched,
        queries=queries,
        searches_used=live,
    )


def _summary(results: list[ReferenceResult], client: SearchClient) -> Summary:
    counts = dict.fromkeys(Verdict, 0)
    for result in results:
        counts[result.verdict] += 1
    checked = (
        counts[Verdict.VERIFIED] + counts[Verdict.METADATA_MISMATCH] + counts[Verdict.NOT_FOUND]
    )
    return Summary(
        total=len(results),
        counts=counts,
        integrity_score=integrity_score(counts),
        checked=checked,
        credits_used=client.credits_used,
        cache_hits=client.cache_hits,
    )


def check_document(
    document: Document,
    client: SearchClient,
    *,
    mode: RunMode,
    concurrency: int = SEARCH.concurrency,
    progress: ProgressCallback | None = None,
    cfg: MatchConfig = MATCH,
) -> Report:
    """Check all references of ``document`` and assemble the report.

    A fatal search error (invalid key, account out of searches) cancels the remaining
    work and propagates. Budget exhaustion does not: the affected references become
    SKIPPED_BUDGET, while cached references are still checked.
    """
    checker = ReferenceChecker(client, mode, cfg)
    originals: dict[str, Reference] = {}
    for reference in document.references:
        originals.setdefault(dedupe_key(reference), reference)

    total = len(document.references)
    done = 0
    lock = threading.Lock()
    results: dict[int, ReferenceResult] = {}

    def record(result: ReferenceResult) -> None:
        nonlocal done
        with lock:
            results[result.reference.index] = result
            done += 1
            current = done
        if progress is not None:
            progress(Progress(current, total, result))

    with ThreadPoolExecutor(
        max_workers=max(1, concurrency), thread_name_prefix="ghostcite"
    ) as pool:
        futures: list[Future[ReferenceResult]] = [
            pool.submit(checker.check, ref) for ref in originals.values()
        ]
        try:
            for future in as_completed(futures):
                record(future.result())
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise

    by_key = {dedupe_key(r.reference): r for r in results.values()}
    for reference in document.references:
        if reference.index in results:
            continue
        original = by_key[dedupe_key(reference)]
        record(
            original.model_copy(
                update={
                    "reference": reference,
                    "searches_used": 0,
                    "duplicate_of": original.reference.index,
                    "reason": f"Duplicate of reference {original.reference.index}. "
                    f"{original.reason}",
                }
            )
        )

    ordered = [results[ref.index] for ref in document.references]
    return Report(
        tool_version=__version__,
        generated_at=datetime.now(tz=UTC),
        source_name=document.source_name,
        source_format=document.source_format,
        mode=mode,
        results=tuple(ordered),
        summary=_summary(ordered, client),
        warnings=document.warnings,
    )
