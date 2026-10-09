"""SARIF 2.1.0 output, so GitHub code scanning can annotate bad ``.bib`` entries in place.

Each problem becomes a result pointing at the line where the BibTeX entry starts.
VERIFIED references produce no result, so a clean bibliography shows no alerts.
Fingerprints come from the citation itself (key and title), so an alert keeps its
identity when unrelated lines move.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from ghostcite.models import ReferenceResult, Report, Verdict

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
FINGERPRINT_KEY = "ghostciteCitation/v1"


@dataclass(frozen=True, slots=True)
class _Rule:
    id: str
    name: str
    level: str
    short: str
    help: str


_RULES: dict[Verdict, _Rule] = {
    Verdict.NOT_FOUND: _Rule(
        "GC001",
        "CitationNotFound",
        "error",
        "Cited work could not be found on Google Scholar",
        "No Google Scholar record matches the cited title. The reference may be fabricated "
        "(a common LLM hallucination) or have a badly wrong title. Verify it manually.",
    ),
    Verdict.METADATA_MISMATCH: _Rule(
        "GC002",
        "CitationMetadataMismatch",
        "warning",
        "Cited work exists, but its metadata is wrong",
        "The work exists, but the cited authors, year, venue or title disagree with the "
        "Google Scholar record. Correct the entry.",
    ),
    Verdict.UNPARSEABLE: _Rule(
        "GC003",
        "CitationUnparseable",
        "warning",
        "Citation could not be parsed",
        "No title could be read from this entry, so it was not checked.",
    ),
    Verdict.SKIPPED_BUDGET: _Rule(
        "GC004",
        "CitationNotChecked",
        "note",
        "Citation was not checked",
        "The search budget ran out, or no cached result was available, before this "
        "citation could be checked. Re-run with a larger --max-searches.",
    ),
}
_RULE_ORDER = list(_RULES)


def _fingerprint(result: ReferenceResult) -> str:
    reference = result.reference
    identity = f"{reference.key or ''}|{reference.fields.title or reference.raw}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def _message(result: ReferenceResult) -> str:
    reference = result.reference
    label = f"[{reference.key}] " if reference.key else f"Reference {reference.index}: "
    title = reference.fields.title
    cited = f"\u201c{title}\u201d: " if title else ""
    return f"{label}{cited}{result.reason}"


def _location(result: ReferenceResult, artifact_uri: str) -> dict[str, Any]:
    physical: dict[str, Any] = {"artifactLocation": {"uri": artifact_uri}}
    if result.reference.line is not None:
        physical["region"] = {"startLine": result.reference.line}
    return {"physicalLocation": physical}


def _sarif_result(result: ReferenceResult, artifact_uri: str) -> dict[str, Any]:
    rule = _RULES[result.verdict]
    properties: dict[str, Any] = {
        "verdict": result.verdict.value,
        "confidence": result.confidence,
    }
    if result.best_match is not None and result.best_match.candidate.link:
        properties["bestMatch"] = result.best_match.candidate.link
    return {
        "ruleId": rule.id,
        "ruleIndex": _RULE_ORDER.index(result.verdict),
        "level": rule.level,
        "message": {"text": _message(result)},
        "locations": [_location(result, artifact_uri)],
        "partialFingerprints": {FINGERPRINT_KEY: _fingerprint(result)},
        "properties": properties,
    }


def render_sarif(report: Report, artifact_uri: str) -> str:
    """Render the report as a SARIF 2.1.0 log with one run."""
    uri = artifact_uri.replace("\\", "/")
    rules = [
        {
            "id": rule.id,
            "name": rule.name,
            "shortDescription": {"text": rule.short},
            "fullDescription": {"text": rule.help},
            "help": {"text": rule.help},
            "defaultConfiguration": {"level": rule.level},
            "properties": {"tags": ["citations", "research-integrity"]},
        }
        for rule in _RULES.values()
    ]
    log = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "GhostCite",
                        "version": report.tool_version,
                        "semanticVersion": report.tool_version,
                        "rules": rules,
                    }
                },
                "results": [
                    _sarif_result(result, uri)
                    for result in report.results
                    if result.verdict is not Verdict.VERIFIED
                ],
                "properties": {
                    "integrityScore": report.summary.integrity_score,
                    "searchesUsed": report.summary.credits_used,
                    "mode": report.mode.value,
                },
            }
        ],
    }
    return json.dumps(log, indent=2, ensure_ascii=False) + "\n"
