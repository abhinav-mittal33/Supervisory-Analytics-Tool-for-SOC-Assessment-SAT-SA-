"""Examiner verdict ontology (build spec Section 5.1), wired end-to-end: a verdict
missing a required field is invalid data, rejected here, not silently accepted as a
partial record. Required fields follow the Evidence Package schema's own annotations
(Section 11), which are more precise than the prose summary in Section 5.1.
"""
from __future__ import annotations

from dataclasses import dataclass

from satsa.evidence.package import EvidencePackage

VERDICTS = {
    "TRUE_SUPERVISORY_FINDING",
    "FALSE_POSITIVE",
    "INCONCLUSIVE",
    "DATA_QUALITY_ISSUE",
    "EXPECTED_LEGITIMATE_BEHAVIOR",
    "DUPLICATE_OF_EXISTING_FINDING",
    "OUT_OF_SCOPE",
}

TRUE_FINDING_SUB_TYPES = {
    "PROCESS_VIOLATION",
    "CAPABILITY_INADEQUACY",
    "CONTROL_FAILURE",
    "GOVERNANCE_GAP",
}

# What each verdict updates (Section 5.1 / 10.6) — used by feedback.py to route
# correctly instead of treating every verdict as a plain success/failure.
BETA_BINOMIAL_SUCCESS = {"TRUE_SUPERVISORY_FINDING"}
BETA_BINOMIAL_FAILURE = {"FALSE_POSITIVE", "OUT_OF_SCOPE"}
NO_POSTERIOR_UPDATE = {"INCONCLUSIVE", "DATA_QUALITY_ISSUE", "EXPECTED_LEGITIMATE_BEHAVIOR", "DUPLICATE_OF_EXISTING_FINDING"}


class InvalidVerdictError(ValueError):
    pass


@dataclass(frozen=True)
class Verdict:
    finding_id: str
    verdict: str
    capability_link: str | None = None
    sub_type: str | None = None
    authority_violated: str | None = None
    duplicate_of_finding_id: str | None = None


def validate_verdict(v: Verdict) -> None:
    if v.verdict not in VERDICTS:
        raise InvalidVerdictError(f"{v.finding_id}: unknown verdict {v.verdict!r} — free-text verdicts are not acceptable")

    if v.verdict == "TRUE_SUPERVISORY_FINDING":
        if v.capability_link is None:
            raise InvalidVerdictError(f"{v.finding_id}: TRUE_SUPERVISORY_FINDING requires capability_link")
        if v.authority_violated is None:
            raise InvalidVerdictError(f"{v.finding_id}: TRUE_SUPERVISORY_FINDING requires authority_violated")
        if v.sub_type not in TRUE_FINDING_SUB_TYPES:
            raise InvalidVerdictError(f"{v.finding_id}: TRUE_SUPERVISORY_FINDING requires a valid sub_type, got {v.sub_type!r}")

    if v.verdict == "DUPLICATE_OF_EXISTING_FINDING" and v.duplicate_of_finding_id is None:
        raise InvalidVerdictError(f"{v.finding_id}: DUPLICATE_OF_EXISTING_FINDING requires duplicate_of_finding_id")


def apply_verdict(package: EvidencePackage, v: Verdict) -> EvidencePackage:
    """Validates, then returns a new EvidencePackage with the verdict fields set —
    the package is otherwise immutable evidence, the verdict is examiner input
    layered on top, never silently merged without validation."""
    validate_verdict(v)
    package.verdict = v.verdict
    package.verdict_capability_link = v.capability_link
    package.verdict_sub_type = v.sub_type
    package.verdict_authority_violated = v.authority_violated
    package.duplicate_of_finding_id = v.duplicate_of_finding_id
    return package
