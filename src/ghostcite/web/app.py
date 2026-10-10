"""Local web UI: upload or paste references, watch progress, read and download the report.

The server is meant for one person on their own machine. It binds to 127.0.0.1 by
default (see ``ghostcite web``), stores nothing on disk, uses no cookies, analytics or
external assets, and refuses work beyond the limits in :class:`ghostcite.config.WebConfig`.
Without an API key it still starts and offers demo mode.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, PackageLoader, select_autoescape

from ghostcite import __version__
from ghostcite.config import WEB, WebConfig
from ghostcite.document import Document, load_document
from ghostcite.errors import GhostCiteError, InputError
from ghostcite.models import Report, RunMode
from ghostcite.pipeline import Progress
from ghostcite.report import OutputFormat, render
from ghostcite.report.html import render_html
from ghostcite.samples import DEMO_BUNDLE, SAMPLE_BIB, samples_dir
from ghostcite.search.budget import SearchBudget
from ghostcite.service import NO_KEY_MESSAGE, RunOptions, TransportFactory, run_check
from ghostcite.settings import Settings, load_settings
from ghostcite.web.jobs import GlobalBudgetError, JobLimitError, JobManager

_ALLOWED_SUFFIXES = frozenset({".pdf", ".bib", ".txt", ""})
_DOWNLOAD_LABELS = {
    OutputFormat.JSON: "JSON",
    OutputFormat.MARKDOWN: "Markdown",
    OutputFormat.HTML: "HTML",
    OutputFormat.SARIF: "SARIF",
}
_CHUNK = 64 * 1024
_EVENT_POLL_SECONDS = 0.2
_HEARTBEAT_SECONDS = 15.0
"""Send an SSE comment this often while a job is quiet, so proxies keep the stream open."""
PROJECT_URL = "https://github.com/vaani1127/GhostCite"
HOSTED_DEMO_MESSAGE = (
    "This hosted copy runs in demo mode only. Run GhostCite locally with your own SerpApi "
    f"key for live checks: {PROJECT_URL}"
)
_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; "
        "base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}


class UnsupportedTypeError(InputError):
    """The upload is not a PDF, .bib or text file (HTTP 415)."""


class UploadTooLargeError(InputError):
    """The upload exceeds ``WebConfig.max_upload_bytes`` (HTTP 413)."""


@dataclass(frozen=True, slots=True)
class DemoFiles:
    """Where demo mode reads its sample document and response bundle."""

    sample: Path
    bundle: Path

    @property
    def available(self) -> bool:
        """True when both files exist (the bundle ships with the repository)."""
        return self.sample.is_file() and self.bundle.is_file()


def default_demo_files() -> DemoFiles | None:
    """The bundled sample and demo data, or ``None`` when samples are not installed."""
    try:
        root = samples_dir()
    except InputError:
        return None
    return DemoFiles(sample=root / SAMPLE_BIB, bundle=root / DEMO_BUNDLE)


def _error(status: int, message: str, **headers: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status, headers=headers or None)


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    """Read an upload in chunks, refusing as soon as it exceeds ``limit`` bytes."""
    data = bytearray()
    while chunk := await upload.read(_CHUNK):
        data.extend(chunk)
        if len(data) > limit:
            raise UploadTooLargeError(
                f"The file is larger than the {limit // 2**20} MiB upload limit."
            )
    return bytes(data)


def create_app(
    settings: Settings | None = None,
    cfg: WebConfig = WEB,
    *,
    demo: DemoFiles | None = None,
    transport_factory: TransportFactory | None = None,
) -> FastAPI:
    """Build the web application. Arguments exist so tests can inject doubles."""
    resolved = settings or load_settings()
    demo_files = demo if demo is not None else default_demo_files()
    templates = Environment(
        loader=PackageLoader("ghostcite", "web/templates"),
        autoescape=select_autoescape(["html", "j2"]),
    )

    def runner(
        document: Document,
        mode: RunMode,
        shared: SearchBudget | None,
        progress: Callable[[Progress], None],
    ) -> Report:
        if resolved.hosted_demo and mode is not RunMode.DEMO:
            # Second guard behind the HTTP check: a hosted demo never builds a live client.
            raise InputError(HOSTED_DEMO_MESSAGE)
        options = RunOptions(
            mode=mode,
            max_searches=cfg.per_job_search_cap,
            demo_bundle=demo_files.bundle if demo_files is not None else None,
            surface="web",
        )
        extra: dict[str, Any] = {}
        if transport_factory is not None:
            extra["transport_factory"] = transport_factory
        return run_check(
            document, resolved, options, progress=progress, shared_budget=shared, **extra
        )

    jobs = JobManager(runner, cfg)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        jobs.shutdown()

    app = FastAPI(
        title="GhostCite",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.jobs = jobs
    app.mount("/static", StaticFiles(packages=[("ghostcite", "web/static")]), name="static")

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    def demo_ready() -> bool:
        return demo_files is not None and demo_files.available

    # In a hosted demo, live checks are off even if a key happens to be configured.
    live_enabled = resolved.has_api_key and not resolved.hosted_demo

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return templates.get_template("index.html.j2").render(
            has_key=live_enabled,
            hosted=resolved.hosted_demo,
            project_url=PROJECT_URL,
            demo_ready=demo_ready(),
            cfg=cfg,
            version=__version__,
        )

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        return {
            "version": __version__,
            "has_api_key": live_enabled,
            "hosted_demo": resolved.hosted_demo,
            "demo_available": demo_ready(),
            "limits": {
                "max_upload_bytes": cfg.max_upload_bytes,
                "per_job_search_cap": cfg.per_job_search_cap,
                "max_references_per_job": cfg.max_references_per_job,
                "max_concurrent_jobs": cfg.max_concurrent_jobs,
                "global_searches_left": jobs.global_budget.remaining,
            },
        }

    async def read_input(
        file: UploadFile | None, text: str | None, sample: bool
    ) -> tuple[bytes, str | None]:
        provided = [file is not None and bool(file.filename), bool(text and text.strip()), sample]
        if sum(provided) != 1:
            raise InputError("Provide exactly one input: a file, pasted text, or the sample.")
        if sample:
            if demo_files is None or not demo_files.available:
                raise InputError("The sample and demo data are not available in this install.")
            return demo_files.sample.read_bytes(), demo_files.sample.name
        if text is not None and text.strip():
            data = text.encode("utf-8")
            if len(data) > cfg.max_upload_bytes:
                raise UploadTooLargeError("The pasted text is larger than the upload limit.")
            return data, None
        if file is None:
            raise InputError("No file was uploaded.")
        suffix = PurePath(file.filename or "").suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise UnsupportedTypeError(
                "Unsupported file type. Upload a PDF, a .bib file or a plain-text reference list."
            )
        return await _read_limited(file, cfg.max_upload_bytes), file.filename

    @app.post("/api/check", status_code=202)
    async def check(
        request: Request,
        file: Annotated[UploadFile | None, File()] = None,
        text: Annotated[str | None, Form()] = None,
        mode: Annotated[str, Form()] = "live",
        sample: Annotated[bool, Form()] = False,
    ) -> Response:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > cfg.max_upload_bytes + _CHUNK:
            return _error(
                413, f"The upload is larger than the {cfg.max_upload_bytes // 2**20} MiB limit."
            )
        run_mode = RunMode.DEMO if sample or mode == RunMode.DEMO.value else RunMode.LIVE
        if run_mode is RunMode.LIVE and resolved.hosted_demo:
            return _error(403, HOSTED_DEMO_MESSAGE)
        if run_mode is RunMode.DEMO and not demo_ready():
            return _error(503, "Demo data is not available in this install.")
        if run_mode is RunMode.LIVE and not resolved.has_api_key:
            return _error(400, NO_KEY_MESSAGE.replace("--demo", "demo mode"))
        try:
            data, filename = await read_input(file, text, sample)
            document = await asyncio.to_thread(load_document, data, filename)
        except UnsupportedTypeError as exc:
            return _error(415, exc.message)
        except UploadTooLargeError as exc:
            return _error(413, exc.message)
        except InputError as exc:
            return _error(422, exc.message)
        if len(document.references) > cfg.max_references_per_job:
            return _error(
                422,
                f"This document has {len(document.references)} references; the web UI checks at "
                f"most {cfg.max_references_per_job} per job. "
                "Use the ghostcite CLI for larger lists.",
            )
        try:
            job = jobs.submit(document, run_mode)
        except JobLimitError as exc:
            return _error(429, exc.message, **{"Retry-After": "30"})
        except GlobalBudgetError as exc:
            return _error(429, exc.message)
        return JSONResponse(
            {
                "job_id": job.id,
                "status_url": f"/api/jobs/{job.id}",
                "events_url": f"/api/jobs/{job.id}/events",
                "report_url": f"/jobs/{job.id}",
                "references": job.total,
                "warnings": list(document.warnings),
            },
            status_code=202,
        )

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> Response:
        job = jobs.get(job_id)
        if job is None:
            return _error(404, "Unknown or expired job.")
        return JSONResponse(job.snapshot())

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str) -> Response:
        job = jobs.get(job_id)
        if job is None:
            return _error(404, "Unknown or expired job.")

        async def stream() -> AsyncIterator[str]:
            sent = 0
            quiet = 0.0
            while True:
                events, finished = job.events_since(sent)
                for event in events:
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
                sent += len(events)
                if finished and not events:
                    return
                quiet = 0.0 if events else quiet + _EVENT_POLL_SECONDS
                if quiet >= _HEARTBEAT_SECONDS:
                    quiet = 0.0
                    yield ": keep-alive\n\n"
                await asyncio.sleep(_EVENT_POLL_SECONDS)

        # Reverse proxies (Render, nginx) must not buffer the progress stream.
        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    def finished_report(job_id: str) -> Report | Response:
        job = jobs.get(job_id)
        if job is None:
            return _error(404, "Unknown or expired job.")
        snapshot = job.snapshot()
        if job.report is None:
            message = snapshot.get("error") or "The check is still running."
            return _error(409, message)
        return job.report

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(job_id: str) -> Response:
        report = finished_report(job_id)
        if isinstance(report, Response):
            return report
        downloads = [
            (_DOWNLOAD_LABELS[fmt], f"/api/jobs/{job_id}/report{fmt.extension}")
            for fmt in OutputFormat
        ]
        return HTMLResponse(render_html(report, downloads=downloads, home_url="/"))

    @app.get("/api/jobs/{job_id}/report.{extension}")
    def download(job_id: str, extension: str) -> Response:
        try:
            output_format = next(f for f in OutputFormat if f.extension == f".{extension}")
        except StopIteration:
            return _error(404, "Unknown report format.")
        report = finished_report(job_id)
        if isinstance(report, Response):
            return report
        body = render(report, output_format)
        filename = f"ghostcite-report{output_format.extension}"
        return Response(
            body,
            media_type=output_format.media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.exception_handler(GhostCiteError)
    async def ghostcite_error(_: Request, exc: GhostCiteError) -> Response:
        return _error(400, exc.message)

    return app
