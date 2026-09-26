"""Expert-agreement mechanism — the buildable half of PS Section 8's validation
requirement. No real NCIIPC expert-review data exists or is obtainable in this
environment; nothing here fabricates it. This module computes a real agreement
metric the moment real verdicts exist (recorded via the already-built examiner
verdict flow, `evidence/verdict.py::apply_verdict`, wired end-to-end in `ui/app.py`).

Docstring and every UI surface that renders `AgreementReport` must state plainly:
this reflects whoever recorded verdicts in this session, not certified NCIIPC
expert output.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from satsa.evidence.package import EvidencePackage
from satsa.evidence.verdict import BETA_BINOMIAL_SUCCESS


@dataclass(frozen=True)
class AgreementReport:
    total_verdicted: int
    confirmed_true: int
    confirmation_rate: float | None  # None if total_verdicted == 0 — no verdicts recorded yet
    by_finding_type: dict[str, tuple] = field(default_factory=dict)  # finding_type -> (verdicted, confirmed)
    by_authority: dict[str, tuple] = field(default_factory=dict)


def compute_agreement(concerns: list[EvidencePackage]) -> AgreementReport:
    verdicted = [c for c in concerns if c.verdict is not None]
    confirmed = [c for c in verdicted if c.verdict in BETA_BINOMIAL_SUCCESS]

    def _breakdown(key_fn) -> dict[str, tuple]:
        result: dict[str, list[int]] = {}
        for c in verdicted:
            key = key_fn(c)
            result.setdefault(key, [0, 0])
            result[key][0] += 1
            if c.verdict in BETA_BINOMIAL_SUCCESS:
                result[key][1] += 1
        return {k: tuple(v) for k, v in result.items()}

    return AgreementReport(
        total_verdicted=len(verdicted),
        confirmed_true=len(confirmed),
        confirmation_rate=(len(confirmed) / len(verdicted)) if verdicted else None,
        by_finding_type=_breakdown(lambda c: c.finding_type),
        by_authority=_breakdown(lambda c: c.authority),
    )
