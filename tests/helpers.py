"""Shared test doubles: recorded responses, scripted transports and reference texts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ghostcite.search.cache import cache_key
from tests.conftest import FIXTURES

# References whose planned queries are answered by the recorded fixtures.
ATTENTION = '[1] A. Vaswani, N. Shazeer, N. Parmar, "Attention is all you need," in NeurIPS, 2017.'
RESNET = (
    "[2] K. He, X. Zhang, S. Ren, J. Sun, "
    '"Deep residual learning for image recognition," in Proc. CVPR, 2016.'
)
WRONG_YEAR = '[3] A. Vaswani, N. Shazeer, N. Parmar, "Attention is all you need," in NeurIPS, 2019.'
FABRICATED = (
    '[4] P. Raghunathan, "Quantum gradient folding for multilingual citation graphs," '
    "J. Imag. Comput., 2021."
)
BOOK = '[5] A. P. J. Abdul Kalam, "Wings of Fire: An Autobiography," Universities Press, 1999.'


def recorded_responses() -> dict[str, dict[str, Any]]:
    """Cache key -> sanitized response, for every recorded SerpApi fixture."""
    responses: dict[str, dict[str, Any]] = {}
    for path in sorted((FIXTURES / "serpapi").glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        responses[cache_key(fixture["params"])] = fixture["response"]
    return responses


def no_results_response() -> dict[str, Any]:
    """The documented shape of a successful search with zero results."""
    return {
        "search_metadata": {"status": "Success"},
        "error": "Google hasn't returned any results for this query.",
    }


class FixtureTransport:
    """A live transport double that answers from recorded fixtures.

    Unrecorded queries get the "no results" response, the way SerpApi answers a
    fabricated title. Every call is recorded so tests can assert how many credits a run
    would have spent.
    """

    def __init__(self, extra: Mapping[str, dict[str, Any]] | None = None) -> None:
        self.responses = {**recorded_responses(), **(extra or {})}
        self.calls: list[dict[str, str]] = []
        self.account_calls = 0
        self.searches_left = 200
        self.hourly_limit = 250

    def search(self, params: Mapping[str, str]) -> dict[str, Any]:
        self.calls.append(dict(params))
        return self.responses.get(cache_key(params), no_results_response())

    def account(self) -> dict[str, Any]:
        self.account_calls += 1
        return {
            "total_searches_left": self.searches_left,
            "account_rate_limit_per_hour": self.hourly_limit,
        }


def numbered(*references: str) -> str:
    """Join references into one list, renumbered [1], [2], ... in the given order."""
    lines = []
    for index, reference in enumerate(references, 1):
        body = reference.split("] ", 1)[1] if reference.startswith("[") else reference
        lines.append(f"[{index}] {body}")
    return "\n".join(lines)


def demo_bundle_payload() -> dict[str, Any]:
    """A demo bundle (current file format) holding every recorded fixture."""
    entries = []
    for path in sorted((FIXTURES / "serpapi").glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        entries.append({"params": fixture["params"], "response": fixture["response"]})
    return {"format": 1, "entries": entries}
