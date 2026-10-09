"""Background check jobs for the web UI: admission control, progress events, expiry.

Safety limits (``WebConfig``) are enforced here:

* at most ``max_concurrent_jobs`` jobs run at once; more are refused, not queued, so a
  busy laptop never builds an invisible backlog of credit-spending work;
* every live job has its own cap (``per_job_search_cap``) plus one budget shared by all
  jobs of the process (``global_search_budget``);
* finished jobs, including their reports, are forgotten after ``job_ttl_seconds``.
  Nothing is written to disk: uploads are processed in memory.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ghostcite.config import WEB, WebConfig
from ghostcite.document import Document
from ghostcite.errors import GhostCiteError
from ghostcite.logs import get_logger
from ghostcite.models import Report, RunMode
from ghostcite.pipeline import Progress
from ghostcite.search.budget import SearchBudget

_log = get_logger(__name__)


class JobState(StrEnum):
    """Lifecycle of a check job."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    """One document being checked; mutated only under ``lock``."""

    id: str
    mode: RunMode
    total: int
    created: float
    state: JobState = JobState.RUNNING
    done: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    report: Report | None = None
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self) -> dict[str, Any]:
        """JSON-safe view of the job for the status endpoint."""
        with self.lock:
            payload: dict[str, Any] = {
                "id": self.id,
                "state": self.state.value,
                "mode": self.mode.value,
                "done": self.done,
                "total": self.total,
            }
            if self.error is not None:
                payload["error"] = self.error
            if self.report is not None:
                summary = self.report.summary
                payload["summary"] = {
                    "integrity_score": summary.integrity_score,
                    "counts": {k.value: v for k, v in summary.counts.items()},
                    "credits_used": summary.credits_used,
                }
            return payload

    def events_since(self, index: int) -> tuple[list[dict[str, Any]], bool]:
        """Events after ``index`` and whether the job has finished."""
        with self.lock:
            return self.events[index:], self.state is not JobState.RUNNING


class JobLimitError(GhostCiteError):
    """The server is at its concurrent-job limit."""


class GlobalBudgetError(GhostCiteError):
    """The server's shared search budget is used up."""


Runner = Callable[[Document, RunMode, SearchBudget | None, Callable[[Progress], None]], Report]
"""Runs one check: ``(document, mode, shared_budget, progress_callback) -> report``."""


class JobManager:
    """Starts, tracks and expires check jobs. Safe to use from request handlers."""

    def __init__(
        self,
        runner: Runner,
        cfg: WebConfig = WEB,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._runner = runner
        self._cfg = cfg
        self._clock = clock
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(cfg.max_concurrent_jobs)
        self._pool = ThreadPoolExecutor(
            max_workers=cfg.max_concurrent_jobs, thread_name_prefix="ghostcite-job"
        )
        self.global_budget = SearchBudget(cfg.global_search_budget)

    def shutdown(self) -> None:
        """Stop accepting work and wait for running jobs."""
        self._pool.shutdown(wait=True, cancel_futures=True)

    def get(self, job_id: str) -> Job | None:
        """The job with ``job_id``, if it exists and has not expired."""
        self._expire()
        with self._lock:
            return self._jobs.get(job_id)

    def submit(self, document: Document, mode: RunMode) -> Job:
        """Start checking ``document`` in the background, or refuse with a clear error."""
        self._expire()
        if mode is RunMode.LIVE and self.global_budget.remaining <= 0:
            raise GlobalBudgetError(
                "This GhostCite server has used its whole search budget "
                f"({self._cfg.global_search_budget} searches). Restart it to reset the "
                "budget, or use demo mode."
            )
        if not self._slots.acquire(blocking=False):
            raise JobLimitError(
                f"{self._cfg.max_concurrent_jobs} checks are already running. "
                "Please wait for one to finish and try again."
            )
        job = Job(
            id=uuid.uuid4().hex,
            mode=mode,
            total=len(document.references),
            created=self._clock(),
        )
        with self._lock:
            self._jobs[job.id] = job
        self._pool.submit(self._run, job, document)
        return job

    def _run(self, job: Job, document: Document) -> None:
        def progress(event: Progress) -> None:
            with job.lock:
                job.done = event.done
                job.events.append(
                    {
                        "type": "progress",
                        "done": event.done,
                        "total": event.total,
                        "index": event.result.reference.index,
                        "verdict": event.result.verdict.value,
                    }
                )

        shared = self.global_budget if job.mode is RunMode.LIVE else None
        try:
            report = self._runner(document, job.mode, shared, progress)
        except GhostCiteError as exc:
            with job.lock:
                job.state, job.error = JobState.FAILED, exc.message
                job.events.append({"type": "error", "message": exc.message})
        except Exception:  # noqa: BLE001 - a job must never die silently; the cause is logged
            _log.exception("check job %s crashed", job.id)
            message = "An unexpected error occurred while checking this document."
            with job.lock:
                job.state, job.error = JobState.FAILED, message
                job.events.append({"type": "error", "message": message})
        else:
            with job.lock:
                job.report, job.state = report, JobState.DONE
                job.events.append({"type": "done", "url": f"/jobs/{job.id}"})
        finally:
            self._slots.release()

    def _expire(self) -> None:
        cutoff = self._clock() - self._cfg.job_ttl_seconds
        with self._lock:
            for job_id in [
                jid
                for jid, job in self._jobs.items()
                if job.created < cutoff and job.state is not JobState.RUNNING
            ]:
                del self._jobs[job_id]
