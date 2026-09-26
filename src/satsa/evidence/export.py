"""Structured Evidence Package export (build spec Section 11's own schema, made
downloadable) — a well-formed JSON document an examiner can keep, forward, or
attach to a case file, independent of this tool's own UI. No LLM, no template
prose — a direct, complete serialization of the same dataclass the analytical core
already produces, so the export can never drift from what the UI shows.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from satsa.evidence.package import EvidencePackage


def evidence_package_to_dict(pkg: EvidencePackage) -> dict:
    return asdict(pkg)


def export_evidence_package(pkg: EvidencePackage) -> str:
    """One finding, pretty-printed JSON."""
    return json.dumps(evidence_package_to_dict(pkg), indent=2)


def export_evidence_packages(concerns: list[EvidencePackage], *, cse_id: str | None = None) -> str:
    """A whole entity's (or assessment's) findings as one JSON document — a
    generated_at timestamp is deliberately NOT included here (would make the byte
    content non-deterministic and untestable for no examiner-facing benefit); the
    per-package provenance/verdict fields already carry the real timestamps that
    matter."""
    return json.dumps(
        {
            "cse_id": cse_id,
            "finding_count": len(concerns),
            "findings": [evidence_package_to_dict(c) for c in concerns],
        },
        indent=2,
    )
