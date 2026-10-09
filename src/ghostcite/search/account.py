"""Credit preflight and pacing from the free SerpApi Account API.

The Account API response also contains the API key and the account e-mail address.
Only the numeric fields below are ever read. The payload itself is never logged,
stored or returned.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from ghostcite.config import SEARCH, SearchConfig
from ghostcite.errors import InsufficientCreditsError


@dataclass(frozen=True, slots=True)
class AccountQuota:
    """The only facts GhostCite keeps about the account."""

    searches_left: int
    hourly_limit: int | None


class AccountSource(Protocol):
    """Something that can fetch the raw Account API payload (``LiveTransport`` in production)."""

    def account(self) -> dict[str, Any]:
        """Return the Account API JSON."""


def _count(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def parse_quota(payload: Mapping[str, Any]) -> AccountQuota:
    """Extract the remaining searches and the hourly limit; ignore everything else.

    ``total_searches_left`` includes any extra credits beyond the plan, so it is
    preferred over ``plan_searches_left``.
    """
    left = _count(payload, "total_searches_left")
    if left is None:
        left = _count(payload, "plan_searches_left")
    return AccountQuota(
        searches_left=max(0, left or 0),
        hourly_limit=_count(payload, "account_rate_limit_per_hour"),
    )


def fetch_quota(source: AccountSource) -> AccountQuota:
    """Read the quota from the Account API, which does not cost a search."""
    return parse_quota(source.account())


def estimate_searches(
    uncached_references: int, max_searches: int, cfg: SearchConfig = SEARCH
) -> int:
    """Expected live searches for a run: the planner average, capped by the run budget."""
    expected = math.ceil(uncached_references * cfg.expected_searches_per_reference)
    return min(max_searches, expected)


def check_quota(quota: AccountQuota, estimate: int) -> None:
    """Refuse to start a run that the account cannot pay for, before any credit is spent."""
    if quota.searches_left < estimate:
        raise InsufficientCreditsError(
            f"This run needs about {estimate} searches, but the SerpApi account has only "
            f"{quota.searches_left} left. Lower --max-searches, check fewer references, "
            "or use --offline to rely on cached results."
        )


def pacing_rate(quota: AccountQuota, cfg: SearchConfig = SEARCH) -> float | None:
    """Searches per hour to pace at, or ``None`` when the account reports no limit."""
    if not quota.hourly_limit:
        return None
    return max(1.0, quota.hourly_limit * cfg.rate_limit_safety_fraction)
