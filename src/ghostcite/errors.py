"""Exception hierarchy and the process exit codes it maps to.

Every user-facing failure is a :class:`GhostCiteError`. Its message is redacted when
the exception is created, so a key can never leak through ``str(exc)``, a traceback or
the web API's error JSON.
"""

from __future__ import annotations

from enum import IntEnum

from ghostcite.redact import redact


class ExitCode(IntEnum):
    """Documented exit codes of the ``ghostcite`` CLI."""

    OK = 0
    """All references passed the ``--fail-on`` threshold."""
    CITATIONS_FAILED = 1
    """At least ``--fail-on`` references were NOT_FOUND or METADATA_MISMATCH."""
    USAGE = 2
    """Bad arguments or unreadable input."""
    SERVICE = 3
    """SerpApi or network failure, or not enough credits to run."""


class GhostCiteError(Exception):
    """Base class for errors that should be shown to the user as a clean message."""

    exit_code: ExitCode = ExitCode.USAGE

    def __init__(self, message: str) -> None:
        self.message = redact(message)
        super().__init__(self.message)


class InputError(GhostCiteError):
    """The input file or text cannot be processed (wrong type, too big, empty …)."""

    exit_code = ExitCode.USAGE


class ScannedPdfError(InputError):
    """The PDF contains no extractable text, most likely a scan."""


class SearchServiceError(GhostCiteError):
    """SerpApi rejected the request or could not be reached."""

    exit_code = ExitCode.SERVICE


class InsufficientCreditsError(SearchServiceError):
    """The account has fewer searches left than the run is expected to need."""


class BudgetExhaustedError(GhostCiteError):
    """Internal signal: the run's search budget is spent.

    The pipeline catches it and marks the remaining references SKIPPED_BUDGET, so it
    never reaches the user as a failure.
    """

    exit_code = ExitCode.OK
