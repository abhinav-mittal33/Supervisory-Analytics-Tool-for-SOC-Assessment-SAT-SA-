from satsa.evidence.package import EvidencePackage
from satsa.portfolio.entity_risk import EntityRiskIndicator
from satsa.reporting.report_builder import build_report
from satsa.temporal.cycles import TrendClassification


def _concern(finding_id, finding_type, notes):
    return EvidencePackage(
        finding_id=finding_id, finding_type=finding_type, capability="Escalation", authority="MANDATORY",
        rule_id=None, rule_version=None, anomaly_score=1.0, finding_score=1.0, concern_score=1.0,
        confidence=0.9, evidence_quality="HIGH", estimated_review_cost_minutes=10.0,
        affected_objects=["CASE001"], assumptions=notes,
    )


def test_report_contains_every_entity_and_its_tier():
    indicators = [
        EntityRiskIndicator(cse_id="CSE_A", entity_risk_score=3.0, entity_risk_tier="HIGH"),
        EntityRiskIndicator(cse_id="CSE_B", entity_risk_score=0.0, entity_risk_tier="LOW"),
    ]
    report = build_report(indicators, top_concerns={})
    assert "CSE_A" in report and "HIGH" in report
    assert "CSE_B" in report and "LOW" in report


def test_report_contains_every_supplied_concerns_finding_id():
    concerns = [_concern("FIND00001", "ESCALATION_SLA_VIOLATION", ["some rationale"])]
    report = build_report([], top_concerns={"CSE_A": concerns})
    assert "FIND00001" in report
    assert "ESCALATION_SLA_VIOLATION" in report


def test_no_trend_data_produces_an_honest_placeholder_not_fabricated_numbers():
    report = build_report([], top_concerns={}, trend=None)
    assert "not yet run" in report


def test_trend_data_is_rendered_when_supplied():
    report = build_report([], top_concerns={}, trend={"REASSIGNMENT_LOOP": TrendClassification.VERIFIED_IMPROVEMENT})
    assert "VERIFIED_IMPROVEMENT" in report


def test_untrusted_finding_content_is_html_escaped_not_injected():
    malicious = _concern("FIND00002", "ESCALATION_SLA_VIOLATION", ["<script>alert(1)</script>"])
    report = build_report([], top_concerns={"CSE_A": [malicious]})
    assert "<script>alert(1)</script>" not in report
    assert "&lt;script&gt;" in report
