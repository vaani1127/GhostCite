"""Web UI and API: happy paths, every safety limit, and the no-key demo experience."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ghostcite.config import WEB, SearchConfig, WebConfig
from ghostcite.errors import SearchServiceError
from ghostcite.models import RunMode
from ghostcite.service import TransportFactory
from ghostcite.settings import Settings
from ghostcite.web import app as web_app
from ghostcite.web.app import HOSTED_DEMO_MESSAGE, PROJECT_URL, DemoFiles, create_app
from tests.helpers import (
    ATTENTION,
    FABRICATED,
    RESNET,
    FixtureTransport,
    demo_bundle_payload,
    numbered,
)

SAMPLE_BIB = (
    "@inproceedings{vaswani2017, title={Attention is all you need}, "
    "author={Vaswani, Ashish and Shazeer, Noam}, booktitle={NeurIPS}, year={2017}}\n"
)


def _factory(transport: FixtureTransport) -> TransportFactory:
    def build(settings: Settings, cfg: SearchConfig) -> FixtureTransport:
        return transport

    return build


@pytest.fixture
def demo(tmp_path: Path) -> DemoFiles:
    sample = tmp_path / "sample.bib"
    sample.write_text(SAMPLE_BIB, encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    payload = demo_bundle_payload()
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    return DemoFiles(sample=sample, bundle=bundle)


def _settings(tmp_path: Path, *, key: bool = True, hosted: bool = False) -> Settings:
    return Settings(
        api_key=SecretStr("test-key-not-real") if key else None,
        cache_dir=tmp_path / "cache",
        hosted_demo=hosted,
    )


@pytest.fixture
def transport() -> FixtureTransport:
    return FixtureTransport()


def _client(
    tmp_path: Path,
    demo: DemoFiles | None,
    transport: FixtureTransport | None = None,
    *,
    key: bool = True,
    hosted: bool = False,
    cfg: WebConfig = WEB,
) -> TestClient:
    app = create_app(
        _settings(tmp_path, key=key, hosted=hosted),
        cfg,
        demo=demo,
        transport_factory=_factory(transport or FixtureTransport()),
    )
    return TestClient(app)


@pytest.fixture
def client(tmp_path: Path, demo: DemoFiles, transport: FixtureTransport) -> Iterator[TestClient]:
    with _client(tmp_path, demo, transport) as test_client:
        yield test_client


def _wait(client: TestClient, job_id: str, timeout: float = 10.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status: dict[str, Any] = client.get(f"/api/jobs/{job_id}").json()
        if status["state"] != "running":
            return status
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")


def _submit(client: TestClient, **data: Any) -> Any:
    return client.post("/api/check", data=data)


# ---------------------------------------------------------------- pages


def test_index_with_key(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "No API key found" not in page.text
    assert 'value="live" checked' in page.text
    assert "Try the sample" in page.text
    assert "runs on your machine" in page.text
    assert "hosted demo copy" not in page.text
    assert "LLM-written papers cite papers that do not exist." in page.text
    assert page.text.count('class="step-n"') == 3
    assert "Unavailable" not in page.text


def test_index_without_key_offers_demo(tmp_path: Path, demo: DemoFiles) -> None:
    with _client(tmp_path, demo, key=False) as client:
        page = client.get("/").text
    assert "No API key found: demo mode only." in page
    assert 'value="live" disabled aria-describedby="live-hint"' in page
    assert 'id="live-hint" class="hint">Unavailable: no <code>SERPAPI_API_KEY</code>' in page
    assert 'value="demo" checked' in page
    assert 'id="sample" class="secondary" >' in page


def test_index_without_key_or_demo(tmp_path: Path) -> None:
    missing = DemoFiles(sample=tmp_path / "none.bib", bundle=tmp_path / "none.json")
    with _client(tmp_path, missing, key=False) as client:
        page = client.get("/").text
        status = client.get("/api/status").json()
    assert "The demo data is not installed either." in page
    assert 'id="submit" disabled' in page
    for hint in ("sample-hint", "demo-hint", "submit-hint"):
        assert f'aria-describedby="{hint}"' in page
        assert f'id="{hint}" class="hint">Unavailable' in page
    assert status["demo_available"] is False


def test_status_reports_limits(client: TestClient) -> None:
    status = client.get("/api/status").json()
    assert status["has_api_key"] is True
    assert status["demo_available"] is True
    assert status["limits"]["per_job_search_cap"] == WEB.per_job_search_cap
    assert status["limits"]["global_searches_left"] == WEB.global_search_budget


def test_security_headers_and_static_assets(client: TestClient) -> None:
    page = client.get("/")
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["referrer-policy"] == "no-referrer"
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/docs").status_code == 404  # no API explorer exposed


# ---------------------------------------------------------------- happy paths


def test_pasted_text_end_to_end(client: TestClient, transport: FixtureTransport) -> None:
    response = _submit(client, text=numbered(ATTENTION, RESNET, FABRICATED), mode="live")
    assert response.status_code == 202
    job = response.json()
    assert job["references"] == 3

    status = _wait(client, job["job_id"])
    assert status["state"] == "done"
    assert status["summary"]["counts"]["VERIFIED"] == 2
    assert status["summary"]["counts"]["NOT_FOUND"] == 1
    assert transport.account_calls == 1

    page = client.get(job["report_url"])
    assert page.status_code == 200
    assert "Check another document" in page.text
    assert "Most serious first" in page.text
    for extension, media in [
        ("json", "application/json"),
        ("md", "text/markdown"),
        ("html", "text/html"),
        ("sarif", "application/sarif+json"),
    ]:
        download = client.get(f"/api/jobs/{job['job_id']}/report.{extension}")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith(media)
        assert f'filename="ghostcite-report.{extension}"' in download.headers["content-disposition"]


def test_progress_events_stream(client: TestClient) -> None:
    job = _submit(client, text=numbered(ATTENTION, RESNET), mode="live").json()
    _wait(client, job["job_id"])
    with client.stream("GET", job["events_url"]) as stream:
        body = "".join(stream.iter_text())
    assert body.count("event: progress") == 2
    assert "event: done" in body
    assert f'"/jobs/{job["job_id"]}"' in body


def test_file_upload(client: TestClient) -> None:
    files = {"file": ("refs.bib", SAMPLE_BIB.encode(), "application/x-bibtex")}
    response = client.post("/api/check", files=files, data={"mode": "live"})
    assert response.status_code == 202
    assert _wait(client, response.json()["job_id"])["state"] == "done"


def test_sample_runs_in_demo_mode_without_a_key(tmp_path: Path, demo: DemoFiles) -> None:
    transport = FixtureTransport()
    with _client(tmp_path, demo, transport, key=False) as client:
        response = _submit(client, sample="true", mode="demo")
        assert response.status_code == 202
        status = _wait(client, response.json()["job_id"])
    assert status["mode"] == "demo"
    assert status["summary"]["counts"]["VERIFIED"] == 1
    assert transport.calls == []  # demo mode never searches


def test_bibtex_warnings_are_returned(client: TestClient) -> None:
    text = SAMPLE_BIB + "@article{broken,\n  title = {never closed,\n"
    response = _submit(client, text=text, mode="live")
    assert response.status_code == 202
    assert any("syntax error" in w for w in response.json()["warnings"])


# ---------------------------------------------------------------- refusals


def test_live_mode_without_key_is_refused(tmp_path: Path, demo: DemoFiles) -> None:
    with _client(tmp_path, demo, key=False) as client:
        response = _submit(client, text=numbered(ATTENTION), mode="live")
    assert response.status_code == 400
    assert "demo mode" in response.json()["error"]


def test_demo_mode_without_demo_data(tmp_path: Path) -> None:
    missing = DemoFiles(sample=tmp_path / "none.bib", bundle=tmp_path / "none.json")
    with _client(tmp_path, missing) as client:
        response = _submit(client, sample="true")
    assert response.status_code == 503


@pytest.mark.parametrize(
    ("data", "files"),
    [
        ({}, None),  # nothing
        ({"text": "   "}, None),  # blank text
        ({"text": "[1] Something."}, {"file": ("refs.txt", b"[1] Other.", "text/plain")}),  # both
    ],
)
def test_exactly_one_input_is_required(
    client: TestClient, data: dict[str, str], files: dict[str, Any] | None
) -> None:
    response = client.post("/api/check", data={"mode": "live", **data}, files=files)
    assert response.status_code == 422
    assert "exactly one input" in response.json()["error"]


@pytest.mark.parametrize(
    ("name", "content", "status", "message"),
    [
        ("thesis.docx", b"PK\x03\x04 zipped", 415, "Unsupported file type"),
        ("figure.png", b"\x89PNG\r\n", 415, "Unsupported file type"),
        ("paper.pdf", b"not a real pdf", 422, "not a PDF"),
        ("refs.txt", b"\x00\x01binary", 422, "not text"),
        ("refs.txt", b"  \n\n  ", 422, "empty"),
    ],
)
def test_wrong_or_bad_files(
    client: TestClient, name: str, content: bytes, status: int, message: str
) -> None:
    response = client.post(
        "/api/check",
        files={"file": (name, content, "application/octet-stream")},
        data={"mode": "live"},
    )
    assert response.status_code == status
    assert message in response.json()["error"]


def test_oversized_upload(tmp_path: Path, demo: DemoFiles) -> None:
    cfg = replace(WEB, max_upload_bytes=1_000)
    with _client(tmp_path, demo, cfg=cfg) as client:
        streamed = client.post(
            "/api/check",
            files={"file": ("big.txt", b"x" * 5_000, "text/plain")},
            data={"mode": "live"},
        )
        declared = client.post(
            "/api/check",
            files={"file": ("big.txt", b"x" * 200_000, "text/plain")},
            data={"mode": "live"},
        )
        pasted = _submit(client, text="y" * 5_000, mode="live")
    assert streamed.status_code == 413
    assert declared.status_code == 413
    assert pasted.status_code == 413


def test_too_many_references(tmp_path: Path, demo: DemoFiles) -> None:
    with _client(tmp_path, demo, cfg=replace(WEB, max_references_per_job=2)) as client:
        response = _submit(client, text=numbered(ATTENTION, RESNET, FABRICATED), mode="live")
    assert response.status_code == 422
    assert "at most 2 per job" in response.json()["error"]


def test_global_budget_exhausted(tmp_path: Path, demo: DemoFiles) -> None:
    with _client(tmp_path, demo, cfg=replace(WEB, global_search_budget=0)) as client:
        live = _submit(client, text=numbered(ATTENTION), mode="live")
        sample = _submit(client, sample="true", mode="demo")
    assert live.status_code == 429
    assert "whole search budget" in live.json()["error"]
    assert sample.status_code == 202  # demo mode spends nothing


def test_per_job_search_cap(tmp_path: Path, demo: DemoFiles) -> None:
    with _client(tmp_path, demo, cfg=replace(WEB, per_job_search_cap=1)) as client:
        job = _submit(client, text=numbered(ATTENTION, RESNET), mode="live").json()
        status = _wait(client, job["job_id"])
    assert status["summary"]["counts"]["SKIPPED_BUDGET"] == 1
    assert status["summary"]["credits_used"] == 1


def test_global_budget_is_shared_across_jobs(tmp_path: Path, demo: DemoFiles) -> None:
    with _client(tmp_path, demo, cfg=replace(WEB, global_search_budget=1)) as client:
        first = _wait(
            client, _submit(client, text=numbered(ATTENTION), mode="live").json()["job_id"]
        )
        second = _submit(client, text=numbered(RESNET), mode="live")
        status = client.get("/api/status").json()
    assert first["summary"]["credits_used"] == 1
    assert second.status_code == 429
    assert status["limits"]["global_searches_left"] == 0


def test_concurrent_job_limit(tmp_path: Path, demo: DemoFiles) -> None:
    release = threading.Event()

    class BlockingTransport(FixtureTransport):
        def search(self, params: Any) -> dict[str, Any]:
            release.wait(timeout=10)
            return super().search(params)

    cfg = replace(WEB, max_concurrent_jobs=1)
    with _client(tmp_path, demo, BlockingTransport(), cfg=cfg) as client:
        first = _submit(client, text=numbered(ATTENTION), mode="live")
        second = _submit(client, text=numbered(RESNET), mode="live")
        release.set()
        _wait(client, first.json()["job_id"])
        third = _submit(client, text=numbered(RESNET), mode="live")
    assert first.status_code == 202
    assert second.status_code == 429
    assert second.headers["retry-after"] == "30"
    assert "already running" in second.json()["error"]
    assert third.status_code == 202


# ---------------------------------------------------------------- jobs


def test_failed_job_reports_the_error(tmp_path: Path, demo: DemoFiles) -> None:
    class RejectingTransport(FixtureTransport):
        def search(self, params: Any) -> dict[str, Any]:
            raise SearchServiceError("SerpApi rejected the API key (HTTP 401).")

    with _client(tmp_path, demo, RejectingTransport()) as client:
        job = _submit(client, text=numbered(ATTENTION), mode="live").json()
        status = _wait(client, job["job_id"])
        report = client.get(f"/api/jobs/{job['job_id']}/report.json")
        with client.stream("GET", job["events_url"]) as stream:
            events = "".join(stream.iter_text())
    assert status["state"] == "failed"
    assert "rejected the API key" in status["error"]
    assert report.status_code == 409
    assert "event: error" in events


def test_unknown_jobs_and_formats(client: TestClient) -> None:
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/jobs/nope/events").status_code == 404
    assert client.get("/jobs/nope").status_code == 404
    job = _submit(client, text=numbered(ATTENTION), mode="live").json()
    _wait(client, job["job_id"])
    assert client.get(f"/api/jobs/{job['job_id']}/report.exe").status_code == 404


# ---------------------------------------------------------------- hosted demo


def test_hosted_index_offers_only_demo(tmp_path: Path, demo: DemoFiles) -> None:
    with _client(tmp_path, demo, hosted=True) as client:  # a key is set, on purpose
        page = client.get("/").text
        status = client.get("/api/status").json()
    assert "This hosted copy runs in demo mode only." in page
    assert "Run GhostCite locally with your own SerpApi key for live checks" in page
    assert f'href="{PROJECT_URL}"' in page
    assert 'value="live" disabled aria-describedby="live-hint"' in page
    assert 'id="live-hint" class="hint">Unavailable on this hosted copy' in page
    assert 'value="demo" checked' in page
    assert 'id="sample" class="secondary" >' in page
    assert "No API key found" not in page
    assert "This is a hosted demo copy of GhostCite" in page
    assert "Live checks against Google Scholar need a local run" in page
    assert "runs on your machine" not in page
    assert (status["hosted_demo"], status["has_api_key"], status["demo_available"]) == (
        True,
        False,
        True,
    )


def test_hosted_refuses_live_checks_even_with_a_key(tmp_path: Path, demo: DemoFiles) -> None:
    transport = FixtureTransport()
    with _client(tmp_path, demo, transport, hosted=True) as client:
        pasted = _submit(client, text=numbered(ATTENTION), mode="live")
        files = {"file": ("refs.bib", SAMPLE_BIB.encode(), "application/x-bibtex")}
        uploaded = client.post("/api/check", files=files, data={"mode": "live"})
        default_mode = _submit(client, text=numbered(ATTENTION))  # mode defaults to live
    for response in (pasted, uploaded, default_mode):
        assert response.status_code == 403
        assert response.json()["error"] == HOSTED_DEMO_MESSAGE
    assert (transport.calls, transport.account_calls) == ([], 0)


def test_hosted_sample_runs_in_one_click(tmp_path: Path, demo: DemoFiles) -> None:
    with _client(tmp_path, demo, hosted=True) as client:
        job = _submit(client, sample="true", mode="demo").json()
        status = _wait(client, job["job_id"])
        page = client.get(job["report_url"])
    assert status["state"] == "done"
    assert page.status_code == 200
    assert "Demo (recorded results)" in page.text


def test_hosted_pasted_references_are_skipped_with_a_reason(
    tmp_path: Path, demo: DemoFiles
) -> None:
    text = numbered('J. Smith, "A completely arbitrary paper about soil microbes," X, 2020.')
    with _client(tmp_path, demo, hosted=True) as client:
        job = _submit(client, text=text, mode="demo").json()
        status = _wait(client, job["job_id"])
        report = client.get(f"/api/jobs/{job['job_id']}/report.json").json()
    assert status["state"] == "done"
    (result,) = report["results"]
    assert result["verdict"] == "SKIPPED_BUDGET"
    assert "not part of the bundled demo data" in result["reason"]


def test_hosted_job_runner_never_runs_live(tmp_path: Path, demo: DemoFiles) -> None:
    from ghostcite.document import load_text

    transport = FixtureTransport()
    with _client(tmp_path, demo, transport, hosted=True) as client:
        app: Any = client.app
        job = app.state.jobs.submit(load_text(numbered(ATTENTION)), RunMode.LIVE)
        status = _wait(client, job.id)
    assert status["state"] == "failed"
    assert "demo mode only" in status["error"]
    assert transport.calls == []


def test_progress_stream_sends_heartbeats_and_is_not_buffered(
    tmp_path: Path, demo: DemoFiles, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web_app, "_EVENT_POLL_SECONDS", 0.01)
    monkeypatch.setattr(web_app, "_HEARTBEAT_SECONDS", 0.02)

    class SlowTransport(FixtureTransport):
        def search(self, params: Any) -> dict[str, Any]:
            time.sleep(0.3)
            return super().search(params)

    with _client(tmp_path, demo, SlowTransport()) as client:
        job = _submit(client, text=numbered(ATTENTION), mode="live").json()
        with client.stream("GET", job["events_url"]) as stream:
            headers = stream.headers
            body = "".join(stream.iter_text())
    assert headers["x-accel-buffering"] == "no"
    assert ": keep-alive" in body
    assert "event: done" in body
