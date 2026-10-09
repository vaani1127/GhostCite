from __future__ import annotations

from typing import Any

import pytest

from ghostcite.config import SearchConfig
from ghostcite.errors import InsufficientCreditsError
from ghostcite.search.account import (
    AccountQuota,
    check_quota,
    estimate_searches,
    fetch_quota,
    pacing_rate,
    parse_quota,
)

# Shape of the documented Account API response, with placeholder sensitive values.
PAYLOAD: dict[str, Any] = {
    "account_id": "000000000000000000000000",
    "api_key": "REDACTED",
    "account_email": "someone@example.org",
    "plan_id": "free",
    "searches_per_month": 250,
    "plan_searches_left": 240,
    "total_searches_left": 245,
    "this_month_usage": 10,
    "account_rate_limit_per_hour": 50,
}


class FakeAccountSource:
    def account(self) -> dict[str, Any]:
        return dict(PAYLOAD)


def test_parse_quota_keeps_only_counts() -> None:
    quota = parse_quota(PAYLOAD)
    assert quota == AccountQuota(searches_left=245, hourly_limit=50)
    assert "someone" not in repr(quota)


def test_parse_quota_falls_back_to_plan_searches() -> None:
    payload = {k: v for k, v in PAYLOAD.items() if k != "total_searches_left"}
    assert parse_quota(payload).searches_left == 240


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"total_searches_left": "lots"},
        {"total_searches_left": True},
        {"plan_searches_left": -5},
    ],
)
def test_parse_quota_handles_missing_or_odd_values(payload: dict[str, Any]) -> None:
    quota = parse_quota(payload)
    assert quota.searches_left == 0
    assert quota.hourly_limit is None


def test_fetch_quota_uses_the_source() -> None:
    assert fetch_quota(FakeAccountSource()).searches_left == 245


def test_estimate_is_capped_by_the_run_budget() -> None:
    cfg = SearchConfig(expected_searches_per_reference=1.5)
    assert estimate_searches(10, 50, cfg) == 15
    assert estimate_searches(3, 50, cfg) == 5  # rounded up
    assert estimate_searches(100, 50, cfg) == 50
    assert estimate_searches(0, 50, cfg) == 0


def test_check_quota_refuses_before_spending() -> None:
    check_quota(AccountQuota(10, 50), 10)
    with pytest.raises(InsufficientCreditsError, match=r"needs about 11 searches.*only 10 left"):
        check_quota(AccountQuota(10, 50), 11)


def test_pacing_rate() -> None:
    cfg = SearchConfig(rate_limit_safety_fraction=0.8)
    assert pacing_rate(AccountQuota(100, 50), cfg) == 40.0
    assert pacing_rate(AccountQuota(100, 1), cfg) == 1.0
    assert pacing_rate(AccountQuota(100, None), cfg) is None
    assert pacing_rate(AccountQuota(100, 0), cfg) is None
