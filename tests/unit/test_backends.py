from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import requests
import serpapi
from pydantic import SecretStr

from ghostcite.errors import InputError, SearchServiceError
from ghostcite.redact import register_secret
from ghostcite.search.backends import (
    DEMO_BUNDLE_FORMAT,
    DemoBundle,
    LiveTransport,
    TransportError,
    check_body,
    http_failure,
    search_created_at,
)
from ghostcite.search.cache import cache_key
from tests.conftest import FIXTURES

SECRET = "0123456789abcdef" * 4  # gitleaks:allow (key-shaped placeholder, not a real key)
PARAMS = {"engine": "google_scholar", "q": "x"}


def _http_error(status: int, error: str | None) -> serpapi.HTTPError:
    """Build the exception the serpapi client raises, including a key-bearing URL."""
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps({"error": error} if error else {}).encode()
    response.url = f"https://serpapi.com/search?q=x&api_key={SECRET}"
    original = requests.HTTPError(f"{status} Error for url: {response.url}", response=response)
    return serpapi.HTTPError(original)


class FakeClient:
    """Stands in for serpapi.Client; records the params it was given."""

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.seen: list[dict[str, str]] = []

    def search(self, params: dict[str, str]) -> object:
        params["api_key"] = SECRET  # the real client mutates its argument like this
        self.seen.append(params)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def account(self) -> object:
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def _transport(
    monkeypatch: pytest.MonkeyPatch, outcome: object
) -> tuple[LiveTransport, FakeClient]:
    fake = FakeClient(outcome)
    monkeypatch.setattr(serpapi, "Client", lambda **_: fake)
    return LiveTransport(SecretStr(SECRET), 5.0), fake


# ---------------------------------------------------------------- classification


@pytest.mark.parametrize(
    ("status", "error", "retryable", "fatal_text"),
    [
        (401, "Invalid API key.", None, "rejected the API key"),
        (403, "Account deleted", None, "HTTP 403"),
        (429, "Your account has run out of searches.", None, "run out of searches"),
        (429, "Hourly limit reached.", True, None),
        (500, None, True, None),
        (503, "We couldn't get valid results", True, None),
        (-1, None, True, None),
        (400, "Missing query `q` parameter.", None, "HTTP 400"),
        (404, None, None, "no error message"),
    ],
)
def test_http_failure_classification(
    status: int, error: str | None, retryable: bool | None, fatal_text: str | None
) -> None:
    failure = http_failure(status, error)
    if retryable:
        assert isinstance(failure, TransportError)
        assert failure.retryable
        assert failure.status == status
    else:
        assert isinstance(failure, SearchServiceError)
        assert fatal_text is not None
        assert fatal_text in failure.message


def test_check_body() -> None:
    empty = {"error": "Google hasn't returned any results for this query."}
    assert check_body(empty) is empty
    assert check_body({"organic_results": []}) == {"organic_results": []}
    with pytest.raises(TransportError, match="could not complete") as exc:
        check_body({"error": "We couldn't get valid results for this search."})
    assert exc.value.retryable
    with pytest.raises(TransportError, match="not JSON"):
        check_body("<html>")


# ---------------------------------------------------------------- live transport


def test_live_search_returns_body_and_never_mutates_caller_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport, fake = _transport(monkeypatch, {"organic_results": [{"title": "T"}]})
    params = dict(PARAMS)
    assert transport.search(params) == {"organic_results": [{"title": "T"}]}
    assert "api_key" not in params
    assert fake.seen[0]["api_key"] == SECRET


def test_live_search_unwraps_serp_results(monkeypatch: pytest.MonkeyPatch) -> None:
    results = serpapi.SerpResults({"organic_results": []}, client=None)
    transport, _ = _transport(monkeypatch, results)
    assert transport.search(PARAMS) == {"organic_results": []}


def test_live_search_http_error_is_redacted_and_unchained(monkeypatch: pytest.MonkeyPatch) -> None:
    register_secret(SECRET)
    transport, _ = _transport(monkeypatch, _http_error(401, "Invalid API key."))
    with pytest.raises(SearchServiceError) as exc:
        transport.search(PARAMS)
    assert SECRET not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__suppress_context__


@pytest.mark.parametrize(
    "error",
    [
        serpapi.TimeoutError("timed out"),
        requests.ConnectionError(f"https://serpapi.com/search?api_key={SECRET}"),
        requests.exceptions.ChunkedEncodingError("broken"),
    ],
)
def test_network_errors_are_retryable(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    transport, _ = _transport(monkeypatch, error)
    with pytest.raises(TransportError) as exc:
        transport.search(PARAMS)
    assert exc.value.retryable
    assert SECRET not in exc.value.message


def test_rate_limit_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    transport, _ = _transport(monkeypatch, _http_error(429, "Hourly limit reached."))
    with pytest.raises(TransportError) as exc:
        transport.search(PARAMS)
    assert exc.value.retryable


def test_one_client_per_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> FakeClient:
        created.append(kwargs)
        return FakeClient({"organic_results": []})

    monkeypatch.setattr(serpapi, "Client", factory)
    transport = LiveTransport(SecretStr(SECRET), 7.0)
    transport.search(PARAMS)
    transport.search(PARAMS)
    assert len(created) == 1
    assert created[0]["timeout"] == 7.0


def test_account_success_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    transport, _ = _transport(monkeypatch, {"total_searches_left": 5})
    assert transport.account() == {"total_searches_left": 5}

    transport, _ = _transport(monkeypatch, _http_error(401, "Invalid API key."))
    with pytest.raises(SearchServiceError, match="rejected the API key"):
        transport.account()

    transport, _ = _transport(monkeypatch, serpapi.TimeoutError("slow"))
    with pytest.raises(SearchServiceError, match="Could not read SerpApi account usage"):
        transport.account()

    transport, _ = _transport(monkeypatch, "not json")
    with pytest.raises(TransportError, match="no JSON"):
        transport.account()


# ---------------------------------------------------------------- demo bundle


def _write_bundle(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_demo_bundle_round_trip(tmp_path: Path) -> None:
    body = {"organic_results": [{"title": "T"}]}
    path = _write_bundle(
        tmp_path / "demo.json",
        {"format": DEMO_BUNDLE_FORMAT, "responses": {cache_key(PARAMS): body}},
    )
    bundle = DemoBundle.load(path)
    assert len(bundle) == 1
    assert bundle.get(PARAMS) == body
    assert bundle.contains(PARAMS)
    assert bundle.get({**PARAMS, "q": "other"}) is None
    with pytest.raises(TypeError, match="read-only"):
        bundle.put(PARAMS, body)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"format": 99, "responses": {}}, "unsupported format"),
        ({"format": DEMO_BUNDLE_FORMAT, "responses": []}, "no responses"),
        (["not", "an", "object"], "unsupported format"),
    ],
)
def test_demo_bundle_rejects_bad_files(tmp_path: Path, payload: object, message: str) -> None:
    with pytest.raises(InputError, match=message):
        DemoBundle.load(_write_bundle(tmp_path / "bad.json", payload))


def test_demo_bundle_missing_or_corrupt_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="could not be read"):
        DemoBundle.load(tmp_path / "absent.json")
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    with pytest.raises(InputError, match="could not be read"):
        DemoBundle.load(corrupt)


def test_only_timeouts_may_have_been_billed(monkeypatch: pytest.MonkeyPatch) -> None:
    transport, _ = _transport(monkeypatch, serpapi.TimeoutError("slow"))
    with pytest.raises(TransportError) as timeout:
        transport.search(PARAMS)
    assert timeout.value.maybe_charged

    transport, _ = _transport(monkeypatch, requests.ConnectionError("refused"))
    with pytest.raises(TransportError) as refused:
        transport.search(PARAMS)
    assert not refused.value.maybe_charged


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            {"search_metadata": {"created_at": "2026-10-09 03:58:50 UTC"}},
            datetime(2026, 10, 9, 3, 58, 50, tzinfo=UTC),
        ),
        ({"search_metadata": {"created_at": "yesterday"}}, None),
        ({"search_metadata": {"created_at": 12}}, None),
        ({"search_metadata": "oops"}, None),
        ({}, None),
    ],
)
def test_search_created_at(body: dict[str, Any], expected: datetime | None) -> None:
    assert search_created_at(body) == expected


def test_created_at_format_matches_recorded_responses() -> None:
    fixture = json.loads((FIXTURES / "serpapi" / "scholar_exact_attention.json").read_text("utf-8"))
    assert search_created_at(fixture["response"]) is not None
