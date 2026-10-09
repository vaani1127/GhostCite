"""Where search responses come from: the live SerpApi transport and read-only stores.

``LiveTransport`` is the only code in GhostCite that talks to the network. It wraps the
official ``serpapi`` client and turns every failure into either a retryable
``TransportError`` or a fatal, user-facing ``SearchServiceError``.

The requests library puts the full request URL, including ``api_key``, into its HTTP
error messages. For that reason original exceptions are never chained (``from None``),
and every message passes through :func:`ghostcite.redact.redact`.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import requests
import serpapi
from pydantic import SecretStr

from ghostcite.errors import GhostCiteError, InputError, SearchServiceError
from ghostcite.redact import redact
from ghostcite.search.cache import cache_key
from ghostcite.search.sanitize import sanitize_response, trim_response

NO_RESULTS_MESSAGE = "hasn't returned any results"
"""Fragment of SerpApi's ``error`` text for a successful search with zero results."""
_OUT_OF_SEARCHES = "run out of searches"
DEMO_BUNDLE_FORMAT = 1
_CREATED_AT_FORMAT = "%Y-%m-%d %H:%M:%S UTC"


class TransportError(Exception):
    """A failed request.

    ``retryable`` says whether trying again can help. ``maybe_charged`` marks failures
    where SerpApi may have completed, and billed, the search even though no answer
    arrived: a client-side timeout. This was observed in the live smoke test, where one
    timed-out request still cost a credit.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
        status: int | None = None,
        maybe_charged: bool = False,
    ) -> None:
        self.message = redact(message)
        self.retryable = retryable
        self.status = status
        self.maybe_charged = maybe_charged
        super().__init__(self.message)


class Transport(Protocol):
    """Sends one search request and returns the JSON response."""

    def search(self, params: Mapping[str, str]) -> dict[str, Any]:
        """Perform the search described by ``params`` (which never contain the API key)."""


class ResponseStore(Protocol):
    """A place responses can be read from and written to."""

    def get(self, params: Mapping[str, str]) -> dict[str, Any] | None:
        """Return a stored response, or ``None``."""

    def contains(self, params: Mapping[str, str]) -> bool:
        """True when a response is stored for ``params``."""

    def put(self, params: Mapping[str, str], response: Mapping[str, Any]) -> None:
        """Store a response."""


def http_failure(status: int, error: str | None) -> GhostCiteError | TransportError:
    """Classify a non-2xx SerpApi response (see https://serpapi.com/api-status-and-error-codes)."""
    detail = error or "no error message"
    if status == 401:
        return SearchServiceError(
            "SerpApi rejected the API key (HTTP 401). Check SERPAPI_API_KEY in your .env file."
        )
    if status == 403:
        return SearchServiceError(f"SerpApi refused the request (HTTP 403): {detail}")
    if status == 429 and _OUT_OF_SEARCHES in detail.lower():
        return SearchServiceError(
            "Your SerpApi account has run out of searches. Use --offline to work from "
            "cached results, or --demo to try GhostCite without a key."
        )
    if status == 429 or status >= 500 or status < 0:
        return TransportError(f"HTTP {status}: {detail}", retryable=True, status=status)
    return SearchServiceError(f"SerpApi request failed (HTTP {status}): {detail}")


def search_created_at(body: Mapping[str, Any]) -> datetime | None:
    """When SerpApi originally ran this search, from ``search_metadata.created_at``.

    A response served from SerpApi's one-hour cache carries the *original* search's
    metadata (same ``id``, original ``created_at``). This was verified by repeating a
    recorded request, which was free and returned identical metadata. SerpApi has no
    explicit "cached" flag, so comparing this time with the request time is how a cache
    hit is recognized. The format is ``"2026-10-09 03:58:50 UTC"``.
    """
    metadata = body.get("search_metadata")
    created = metadata.get("created_at") if isinstance(metadata, dict) else None
    if not isinstance(created, str):
        return None
    try:
        return datetime.strptime(created, _CREATED_AT_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def check_body(body: object) -> dict[str, Any]:
    """Validate a 200 response body.

    An ``error`` key on an HTTP 200 is either the normal "no results" case, which is
    returned as a valid empty response, or a failed search ("We couldn't get valid
    results"), which is retryable.
    """
    if not isinstance(body, dict):
        raise TransportError("SerpApi returned a response that is not JSON.", retryable=True)
    error = body.get("error")
    if isinstance(error, str) and NO_RESULTS_MESSAGE not in error:
        raise TransportError(f"SerpApi could not complete the search: {error}", retryable=True)
    return body


class LiveTransport:
    """Sends searches through the official ``serpapi`` client.

    ``requests.Session`` is not guaranteed to be thread-safe, so each worker thread gets
    its own client.
    """

    def __init__(self, api_key: SecretStr, timeout_seconds: float) -> None:
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._local = threading.local()

    def _client(self) -> serpapi.Client:
        client: serpapi.Client | None = getattr(self._local, "client", None)
        if client is None:
            client = serpapi.Client(api_key=self._api_key.get_secret_value(), timeout=self._timeout)
            self._local.client = client
        return client

    def search(self, params: Mapping[str, str]) -> dict[str, Any]:
        """Run one search. The client mutates its params, so it always gets a fresh copy."""
        try:
            results = self._client().search(dict(params))
        except serpapi.HTTPError as exc:
            failure = http_failure(int(exc.status_code), exc.error)
        except serpapi.TimeoutError:
            failure = TransportError("the request timed out", retryable=True, maybe_charged=True)
        except requests.RequestException as exc:
            failure = TransportError(f"network error: {type(exc).__name__}", retryable=True)
        else:
            body = results.as_dict() if isinstance(results, serpapi.SerpResults) else results
            return check_body(body)
        raise failure from None

    def account(self) -> dict[str, Any]:
        """Fetch the Account API payload (free). Callers must keep only the count fields."""
        try:
            payload = self._client().account()
        except serpapi.HTTPError as exc:
            failure = http_failure(int(exc.status_code), exc.error)
        except (serpapi.TimeoutError, requests.RequestException) as exc:
            failure = TransportError(f"network error: {type(exc).__name__}", retryable=True)
        else:
            if not isinstance(payload, dict):
                raise TransportError("The Account API returned no JSON.", retryable=True)
            return payload
        if isinstance(failure, TransportError):
            raise SearchServiceError(f"Could not read SerpApi account usage: {failure.message}")
        raise failure from None


class RecordingStore:
    """A read-only view of a store that remembers every response it served.

    Used to build committed replay bundles (the demo bundle, the evaluation responses)
    from exactly the searches a run needed.
    """

    def __init__(self, store: ResponseStore) -> None:
        self._store = store
        self.served: dict[str, tuple[dict[str, str], dict[str, Any]]] = {}

    def get(self, params: Mapping[str, str]) -> dict[str, Any] | None:
        """Serve from the wrapped store and remember what was served."""
        body = self._store.get(params)
        if body is not None:
            self.served[cache_key(params)] = (dict(params), body)
        return body

    def contains(self, params: Mapping[str, str]) -> bool:
        """True when the wrapped store holds a response for ``params``."""
        return self._store.contains(params)

    def put(self, params: Mapping[str, str], response: Mapping[str, Any]) -> None:
        """Refuse writes: recording must not change the underlying store."""
        raise TypeError("A recording store is read-only.")

    def entries(self) -> list[dict[str, Any]]:
        """Served searches as ``{"params", "response"}`` entries, in a stable order."""
        served = sorted(self.served.values(), key=lambda item: (item[0]["engine"], item[0]["q"]))
        return [{"params": params, "response": body} for params, body in served]


def bundle_payload(entries: Sequence[Mapping[str, Any]], generated: str) -> dict[str, Any]:
    """A replay-bundle file: trimmed, sanitized responses with their readable parameters."""
    return {
        "format": DEMO_BUNDLE_FORMAT,
        "generated": generated,
        "entries": [
            {
                "params": dict(entry["params"]),
                "response": sanitize_response(trim_response(dict(entry["response"]))),
            }
            for entry in entries
        ],
    }


class DemoBundle:
    """Read-only store backed by the committed, sanitized responses in ``samples/demo_cache``.

    It lets judges run GhostCite end to end without an API key. The file lists each bundled
    search as readable parameters plus the recorded response, so anyone can see exactly
    which searches the demo replays. It is indexed by cache key when loaded.
    """

    def __init__(self, responses: Mapping[str, dict[str, Any]]) -> None:
        self._responses = dict(responses)

    @classmethod
    def from_entries(cls, entries: Sequence[Mapping[str, Any]]) -> DemoBundle:
        """Index ``[{"params": {...}, "response": {...}}, ...]`` by cache key."""
        return cls({cache_key(entry["params"]): dict(entry["response"]) for entry in entries})

    @classmethod
    def load(cls, path: Path) -> DemoBundle:
        """Load a bundle file written by ``scripts/build_demo_bundle.py``."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise InputError(f"The demo bundle {path.name} could not be read: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("format") != DEMO_BUNDLE_FORMAT:
            raise InputError(f"The demo bundle {path.name} has an unsupported format.")
        entries = payload.get("entries")
        if not isinstance(entries, list) or not all(
            isinstance(e, dict)
            and isinstance(e.get("params"), dict)
            and isinstance(e.get("response"), dict)
            for e in entries
        ):
            raise InputError(f"The demo bundle {path.name} contains no usable entries.")
        return cls.from_entries(entries)

    def __len__(self) -> int:
        return len(self._responses)

    def get(self, params: Mapping[str, str]) -> dict[str, Any] | None:
        """Return the bundled response for ``params``, if any."""
        return self._responses.get(cache_key(params))

    def contains(self, params: Mapping[str, str]) -> bool:
        """True when the bundle has a response for ``params``."""
        return cache_key(params) in self._responses

    def put(self, params: Mapping[str, str], response: Mapping[str, Any]) -> None:
        """Refuse writes: the demo bundle is a committed, read-only file."""
        raise TypeError("The demo bundle is read-only.")
