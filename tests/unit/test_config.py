from __future__ import annotations

import dataclasses
import math

import pytest

from ghostcite.config import MATCH, SEARCH, WEB, MatchConfig


def test_match_weights_sum_to_one() -> None:
    total = MATCH.weight_title + MATCH.weight_authors + MATCH.weight_year + MATCH.weight_venue
    assert math.isclose(total, 1.0)


def test_title_thresholds_are_ordered() -> None:
    assert 0.0 < MATCH.title_reject < MATCH.title_match <= 1.0


def test_fallback_cap_is_below_a_title_match() -> None:
    # A Google-only match must never look as certain as a confirmed Scholar match.
    assert MATCH.fallback_confidence_cap < MATCH.title_match


def test_web_limits_fit_within_global_budget() -> None:
    assert 0 < WEB.per_job_search_cap <= WEB.global_search_budget
    assert WEB.default_host == "127.0.0.1"


def test_backoff_is_bounded() -> None:
    assert 0 < SEARCH.backoff_base_seconds <= SEARCH.backoff_cap_seconds


def test_configs_are_immutable_but_replaceable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        MATCH.title_match = 0.5  # type: ignore[misc]
    tuned = dataclasses.replace(MATCH, title_match=0.92)
    assert isinstance(tuned, MatchConfig)
    assert tuned.title_match == 0.92


def test_cache_detection_margin_is_below_the_timeout_retry_delay() -> None:
    assert 0 < SEARCH.cache_detection_margin_seconds < SEARCH.timeout_retry_delay_seconds
    assert SEARCH.timeout_seconds == 75.0
