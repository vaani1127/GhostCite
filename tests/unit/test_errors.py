from __future__ import annotations

import pytest

from ghostcite.errors import (
    BudgetExhaustedError,
    ExitCode,
    GhostCiteError,
    InputError,
    InsufficientCreditsError,
    ScannedPdfError,
    SearchServiceError,
)
from ghostcite.redact import REDACTED


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        (InputError, ExitCode.USAGE),
        (ScannedPdfError, ExitCode.USAGE),
        (SearchServiceError, ExitCode.SERVICE),
        (InsufficientCreditsError, ExitCode.SERVICE),
        (BudgetExhaustedError, ExitCode.OK),
    ],
)
def test_exit_codes(error_type: type[GhostCiteError], expected: ExitCode) -> None:
    assert error_type("boom").exit_code is expected


def test_exit_code_values_are_the_documented_ones() -> None:
    assert [int(code) for code in ExitCode] == [0, 1, 2, 3]


def test_message_is_redacted_at_construction() -> None:
    error = SearchServiceError("failed: https://serpapi.com/search?api_key=topsecret1&q=x")
    assert "topsecret1" not in str(error)
    assert REDACTED in error.message
