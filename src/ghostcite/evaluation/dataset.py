"""The labelled evaluation dataset (``eval/dataset.jsonl``).

Real rows are published works identified by a DOI or arXiv ID; their ground truth comes
from Crossref or arXiv (see :mod:`ghostcite.evaluation.validate`), never from GhostCite.
Fabricated rows are made by perturbing a validated real row, or invented outright, and
record exactly which perturbation was applied.
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ghostcite.models import Verdict


class Kind(StrEnum):
    """Whether the cited work exists as cited."""

    REAL = "real"
    FABRICATED = "fabricated"


class Perturbation(StrEnum):
    """How a fabricated row was made."""

    REWORDED_TITLE = "reworded_title"
    SWAPPED_AUTHORS = "swapped_authors"
    WRONG_YEAR = "wrong_year"
    FAKE_VENUE = "fake_venue"
    INVENTED = "invented"


class EvalRow(BaseModel):
    """One labelled reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    kind: Kind
    field: str
    indian: bool
    entry_type: str
    title: str = Field(min_length=1)
    authors: tuple[tuple[str, str], ...] = Field(min_length=1)
    """(family, given) pairs, in citation order."""
    year: int
    venue: str
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    expected: Verdict
    perturbation: Perturbation | None = None
    source: str | None = None
    """Id of the real row a perturbed row was derived from."""

    @model_validator(mode="after")
    def _consistent(self) -> EvalRow:
        if self.kind is Kind.REAL:
            if not (self.doi or self.arxiv_id):
                raise ValueError(f"{self.id}: a real row needs a DOI or an arXiv ID")
            if self.perturbation is not None or self.expected is not Verdict.VERIFIED:
                raise ValueError(f"{self.id}: real rows are unperturbed and expected VERIFIED")
        else:
            if self.perturbation is None:
                raise ValueError(f"{self.id}: a fabricated row needs a perturbation")
            needs_source = self.perturbation is not Perturbation.INVENTED
            if needs_source != (self.source is not None):
                raise ValueError(f"{self.id}: only invented rows have no source row")
            expected = (
                Verdict.NOT_FOUND
                if self.perturbation is Perturbation.INVENTED
                else Verdict.METADATA_MISMATCH
            )
            if self.expected is not expected:
                raise ValueError(
                    f"{self.id}: {self.perturbation.value} rows expect {expected.value}"
                )
        return self

    @property
    def family(self) -> str:
        """Group key: a real row together with the rows derived from it."""
        return self.source or self.id


def load_dataset(path: Path) -> list[EvalRow]:
    """Read and validate every row; ids must be unique and sources must exist."""
    rows = [
        EvalRow.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [row.id for row in rows]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"duplicate row ids: {sorted(duplicates)}")
    real = {row.id for row in rows if row.kind is Kind.REAL}
    missing = [row.id for row in rows if row.source is not None and row.source not in real]
    if missing:
        raise ValueError(f"rows derived from unknown sources: {missing}")
    return rows
