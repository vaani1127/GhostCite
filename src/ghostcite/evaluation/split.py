"""Fixed-seed, stratified tuning/test split.

Rows are split by *family*: a real row and every row perturbed from it always land in
the same split, so the test set never contains a fabrication of a paper that was tuned
on. Families are stratified by type (real only, real with perturbations, invented) and
by field, and each stratum contributes about ``tuning_fraction`` of its families to the
tuning set.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Sequence
from enum import StrEnum

from ghostcite.evaluation.dataset import EvalRow, Kind

DEFAULT_SEED = 20261009
DEFAULT_TUNING_FRACTION = 0.4


class Split(StrEnum):
    """Which part of the dataset a row belongs to."""

    TUNING = "tuning"
    TEST = "test"


def _stratum(family: Sequence[EvalRow]) -> tuple[str, str]:
    root = family[0]
    if root.kind is Kind.FABRICATED:
        kind = "invented"
    elif len(family) > 1:
        kind = "real+perturbed"
    else:
        kind = "real"
    return kind, root.field


def split_rows(
    rows: Sequence[EvalRow],
    seed: int = DEFAULT_SEED,
    tuning_fraction: float = DEFAULT_TUNING_FRACTION,
) -> dict[str, Split]:
    """Assign every row to the tuning or the test split, deterministically."""
    families: dict[str, list[EvalRow]] = defaultdict(list)
    for row in sorted(rows, key=lambda r: (r.source is not None, r.id)):
        families[row.family].append(row)
    strata: dict[tuple[str, str], list[str]] = defaultdict(list)
    for name, members in families.items():
        strata[_stratum(members)].append(name)

    # Systematic sampling: shuffle within each stratum, lay the strata end to end and take
    # every family where the running count of tuning slots steps up. Small strata are
    # then spread across both splits instead of all falling into one of them.
    rng = random.Random(seed)  # noqa: S311 - reproducible sampling, not security
    ordered: list[str] = []
    for key in sorted(strata):
        names = sorted(strata[key])
        rng.shuffle(names)
        ordered.extend(names)
    offset = rng.random()
    assignment: dict[str, Split] = {}
    for position, name in enumerate(ordered):
        steps = math.floor((position + 1) * tuning_fraction + offset)
        steps -= math.floor(position * tuning_fraction + offset)
        split = Split.TUNING if steps else Split.TEST
        for row in families[name]:
            assignment[row.id] = split
    return assignment
