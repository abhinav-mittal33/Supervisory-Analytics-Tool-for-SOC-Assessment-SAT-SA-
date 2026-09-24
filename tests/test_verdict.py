"""Build Order Step 10 — examiner verdict ontology wired end-to-end (Section 5.1):
an invalid/partial verdict must be rejected, not silently accepted."""
import pytest

from satsa.evidence.package import EvidencePackage, Provenance
from satsa.evidence.verdict import InvalidVerdictError, Verdict, apply_verdict, validate_verdict


def _package() -> EvidencePackage:
    return EvidencePackage(
        finding_id="F1", finding_type="REASSIGNMENT_LOOP", capability="Operational Discipline",
        authority="EXPECTED", rule_id=None, rule_version=None, anomaly_score=1.0,
        finding_score=1.0, concern_score=1.0, confidence=1.0, evidence_quality="HIGH",
        estimated_review_cost_minutes=15.0, provenance=Provenance("s", "f", "F1", "b", "t", "1.0"),
    )


def test_valid_true_supervisory_finding_verdict_passes():
    v = Verdict("F1", "TRUE_SUPERVISORY_FINDING", capability_link="Operational Discipline",
                sub_type="PROCESS_VIOLATION", authority_violated="EXPECTED")
    validate_verdict(v)  # must not raise


@pytest.mark.parametrize("missing_field", ["capability_link", "authority_violated", "sub_type"])
def test_true_supervisory_finding_rejects_missing_required_fields(missing_field):
    fields = dict(capability_link="Operational Discipline", authority_violated="EXPECTED", sub_type="PROCESS_VIOLATION")
    fields[missing_field] = None
    v = Verdict("F1", "TRUE_SUPERVISORY_FINDING", **fields)
    with pytest.raises(InvalidVerdictError):
        validate_verdict(v)


def test_duplicate_verdict_requires_duplicate_of_finding_id():
    v = Verdict("F2", "DUPLICATE_OF_EXISTING_FINDING")
    with pytest.raises(InvalidVerdictError):
        validate_verdict(v)
    v2 = Verdict("F2", "DUPLICATE_OF_EXISTING_FINDING", duplicate_of_finding_id="F1")
    validate_verdict(v2)  # must not raise


def test_unknown_verdict_string_rejected():
    with pytest.raises(InvalidVerdictError):
        validate_verdict(Verdict("F1", "PROBABLY_FINE"))


def test_verdicts_with_no_required_fields_pass_with_none():
    for verdict_type in ["FALSE_POSITIVE", "INCONCLUSIVE", "DATA_QUALITY_ISSUE", "EXPECTED_LEGITIMATE_BEHAVIOR", "OUT_OF_SCOPE"]:
        validate_verdict(Verdict("F1", verdict_type))  # must not raise


def test_apply_verdict_sets_fields_on_package():
    pkg = _package()
    v = Verdict("F1", "TRUE_SUPERVISORY_FINDING", capability_link="Operational Discipline",
                sub_type="CONTROL_FAILURE", authority_violated="EXPECTED")
    updated = apply_verdict(pkg, v)
    assert updated.verdict == "TRUE_SUPERVISORY_FINDING"
    assert updated.verdict_sub_type == "CONTROL_FAILURE"
    assert updated.verdict_capability_link == "Operational Discipline"


def test_apply_verdict_rejects_before_mutating():
    pkg = _package()
    bad = Verdict("F1", "TRUE_SUPERVISORY_FINDING")  # missing everything required
    with pytest.raises(InvalidVerdictError):
        apply_verdict(pkg, bad)
    assert pkg.verdict is None, "package must not be mutated when the verdict is invalid"
