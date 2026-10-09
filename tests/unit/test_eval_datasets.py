"""Properties the committed evaluation datasets must keep."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ghostcite.evaluation.dataset import EvalRow, Kind, Perturbation, load_dataset
from ghostcite.match.normalize import canonical_words

EVAL = Path(__file__).resolve().parents[2] / "eval"
V1 = load_dataset(EVAL / "dataset.jsonl")
V2 = load_dataset(EVAL / "dataset_v2.jsonl")


def _papers(rows: list[EvalRow]) -> tuple[set[str], set[tuple[str, ...]]]:
    real = [r for r in rows if r.kind is Kind.REAL]
    dois = {r.doi.casefold() for r in real if r.doi}
    titles = {tuple(canonical_words(r.title)) for r in real}
    return dois, titles


def test_v2_shares_no_paper_with_v1() -> None:
    v1_dois, v1_titles = _papers(V1)
    v2_dois, v2_titles = _papers(V2)
    assert not v1_dois & v2_dois
    assert not v1_titles & v2_titles
    assert not {r.id for r in V1} & {r.id for r in V2}


def test_v2_composition() -> None:
    kinds = Counter(r.kind for r in V2)
    assert kinds[Kind.REAL] >= 15
    assert kinds[Kind.FABRICATED] >= 10
    per_type = Counter(r.perturbation for r in V2 if r.perturbation)
    assert all(per_type[p] >= 2 for p in Perturbation)
    assert sum(r.indian for r in V2 if r.kind is Kind.REAL) >= 6


def test_every_v2_row_passed_validation() -> None:
    validation = json.loads((EVAL / "dataset_v2_validation.json").read_text(encoding="utf-8"))
    assert {r.id for r in V2} == {k for k, v in validation.items() if v["ok"]}
