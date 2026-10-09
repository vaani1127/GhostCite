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
from ghostcite.search.backends import DEMO_BUNDLE_FORMAT
from ghostcite.service import TransportFactory
from ghostcite.settings import Settings
from ghostcite.web.app import DemoFiles, create_app
from tests.helpers import (
    ATTENTION,
    FABRICATED,
    RESNET,
    FixtureTransport,
    numbered,
    recorded_responses,
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
    payload = {"format": DEMO_BUNDLE_FORMAT, "responses": recorded_responses()}
    bundle.write_text(json.dumps(payload), encoding="utf-8")
    return DemoFiles(sample=sample, bundle=bundle)


def _settings(tmp_path: Path, *, key: bool = True) -> Settings:
    return Settings(
        api_key=SecretStr("test-key-not-real") if key else None, cache_dir=tmp_path / "cache"
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
    cfg: WebConfig = WEB,
) -> TestClient:
    app = create_app(
        _settings(tmp_path, key=key),
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


def test_index_without_key_offers_demo(tmp_path: Path, demo: DemoFiles) -> None:
    with _client(tmp_path, demo, key=False) as client:
        page = client.get("/").text
    assert "No API key found: demo mode only." in page
    assert 'value="live" disabled' in page
    assert 'value="demo" checked' in page


def test_index_without_key_or_demo(tmp_path: Path) -> None:
    missing = DemoFiles(sample=tmp_path / "none.bib", bundle=tmp_path / "none.json")
    with _client(tmp_path, missing, key=False) as client:
        page = client.get("/").text
        status = client.get("/api/status").json()
    assert "The demo data is not installed either." in page
    assert 'id="submit" disabled' in page
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
