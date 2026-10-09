from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

from ghostcite.config import WEB
from ghostcite.document import Document, load_text
from ghostcite.models import Report, RunMode
from ghostcite.pipeline import Progress
from ghostcite.search.budget import SearchBudget
from ghostcite.web.jobs import Job, JobManager, JobState


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _wait(job: Job) -> None:
    deadline = time.monotonic() + 5
    while job.state is JobState.RUNNING and time.monotonic() < deadline:
        time.sleep(0.01)


def _document() -> Document:
    return load_text("[1] A. Smith, “A study of citation errors,” 2020.")


def test_crashing_runner_fails_the_job_with_a_generic_message() -> None:
    def crash(
        document: Document,
        mode: RunMode,
        shared: SearchBudget | None,
        progress: Callable[[Progress], None],
    ) -> Report:
        raise RuntimeError("internal detail that must not leak")

    manager = JobManager(crash, WEB)
    job = manager.submit(_document(), RunMode.DEMO)
    _wait(job)
    manager.shutdown()
    snapshot = job.snapshot()
    assert snapshot["state"] == "failed"
    assert "internal detail" not in snapshot["error"]
    assert job.events_since(0)[0][-1]["type"] == "error"


def test_finished_jobs_expire_but_running_ones_do_not() -> None:
    clock = Clock()

    def never_finishes(
        document: Document,
        mode: RunMode,
        shared: SearchBudget | None,
        progress: Callable[[Progress], None],
    ) -> Report:
        raise RuntimeError("done quickly")

    manager = JobManager(never_finishes, replace(WEB, job_ttl_seconds=60), clock=clock)
    job = manager.submit(_document(), RunMode.DEMO)
    _wait(job)
    assert manager.get(job.id) is job
    clock.now += 61
    assert manager.get(job.id) is None
    manager.shutdown()


def test_snapshot_of_a_running_job() -> None:
    job = Job(id="x", mode=RunMode.LIVE, total=3, created=0.0, done=1)
    assert job.snapshot() == {"id": "x", "state": "running", "mode": "live", "done": 1, "total": 3}
    events, finished = job.events_since(0)
    assert (events, finished) == ([], False)
