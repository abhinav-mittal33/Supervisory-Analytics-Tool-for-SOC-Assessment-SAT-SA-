from satsa.evidence.package import EvidencePackage
from satsa.evidence.verdict import Verdict, apply_verdict
from satsa.validation.expert_agreement import compute_agreement


def _package(finding_id, finding_type, authority):
    return EvidencePackage(
        finding_id=finding_id, finding_type=finding_type, capability="Escalation", authority=authority,
        rule_id=None, rule_version=None, anomaly_score=1.0, finding_score=1.0, concern_score=1.0,
        confidence=0.9, evidence_quality="HIGH", estimated_review_cost_minutes=10.0,
    )


def test_no_verdicts_recorded_yet_gives_none_rate_not_zero():
    concerns = [_package("F1", "REASSIGNMENT_LOOP", "EXPECTED")]
    report = compute_agreement(concerns)
    assert report.total_verdicted == 0
    assert report.confirmation_rate is None


def test_confirmation_rate_reflects_only_verdicted_concerns():
    p1 = _package("F1", "REASSIGNMENT_LOOP", "EXPECTED")
    p2 = _package("F2", "REASSIGNMENT_LOOP", "EXPECTED")
    p3 = _package("F3", "MISSING_ENRICHMENT", "EXPECTED")  # never verdicted
    apply_verdict(p1, Verdict("F1", "TRUE_SUPERVISORY_FINDING", capability_link="Escalation", sub_type="PROCESS_VIOLATION", authority_violated="EXPECTED"))
    apply_verdict(p2, Verdict("F2", "FALSE_POSITIVE"))

    report = compute_agreement([p1, p2, p3])
    assert report.total_verdicted == 2
    assert report.confirmed_true == 1
    assert report.confirmation_rate == 0.5


def test_breakdown_by_finding_type_and_authority():
    p1 = _package("F1", "REASSIGNMENT_LOOP", "EXPECTED")
    p2 = _package("F2", "ESCALATION_SLA_VIOLATION", "MANDATORY")
    apply_verdict(p1, Verdict("F1", "TRUE_SUPERVISORY_FINDING", capability_link="Escalation", sub_type="PROCESS_VIOLATION", authority_violated="EXPECTED"))
    apply_verdict(p2, Verdict("F2", "FALSE_POSITIVE"))

    report = compute_agreement([p1, p2])
    assert report.by_finding_type["REASSIGNMENT_LOOP"] == (1, 1)
    assert report.by_finding_type["ESCALATION_SLA_VIOLATION"] == (1, 0)
    assert report.by_authority["MANDATORY"] == (1, 0)
