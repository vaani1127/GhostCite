"""Hard limits on how many live SerpApi searches a run may spend.

A credit is reserved before a request is sent and refunded if the request fails,
because SerpApi does not charge for errored searches. Cache hits never touch a budget.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Protocol


class Budget(Protocol):
    """Anything that can hand out and take back search credits."""

    def reserve(self) -> bool:
        """Take one credit if one is available; return whether it was taken."""

    def refund(self) -> None:
        """Return one previously reserved credit."""

    @property
    def used(self) -> int:
        """Credits currently spent."""


class SearchBudget:
    """A thread-safe counter with a hard cap."""

    def __init__(self, limit: int) -> None:
        if limit < 0:
            raise ValueError("A search budget cannot be negative.")
        self.limit = limit
        self._used = 0
        self._lock = threading.Lock()

    def reserve(self) -> bool:
        """Take one credit if the cap allows it."""
        with self._lock:
            if self._used >= self.limit:
                return False
            self._used += 1
            return True

    def refund(self) -> None:
        """Give back one credit (a failed request is not charged by SerpApi)."""
        with self._lock:
            self._used = max(0, self._used - 1)

    @property
    def used(self) -> int:
        """Credits spent so far."""
        with self._lock:
            return self._used

    @property
    def remaining(self) -> int:
        """Credits still available."""
        with self._lock:
            return self.limit - self._used


class CombinedBudget:
    """Several budgets that must all allow a search, e.g. a per-job cap plus a global cap.

    Reservation is all-or-nothing. If a later budget refuses, the earlier reservations
    are rolled back, so no budget leaks credits.
    """

    def __init__(self, budgets: Sequence[Budget]) -> None:
        if not budgets:
            raise ValueError("CombinedBudget needs at least one budget.")
        self._budgets = tuple(budgets)
        self._lock = threading.Lock()

    def reserve(self) -> bool:
        """Reserve one credit from every budget, or from none."""
        with self._lock:
            taken: list[Budget] = []
            for budget in self._budgets:
                if not budget.reserve():
                    for granted in taken:
                        granted.refund()
                    return False
                taken.append(budget)
            return True

    def refund(self) -> None:
        """Refund one credit to every budget."""
        with self._lock:
            for budget in self._budgets:
                budget.refund()

    @property
    def used(self) -> int:
        """Credits spent, as counted by the first (innermost) budget."""
        return self._budgets[0].used
