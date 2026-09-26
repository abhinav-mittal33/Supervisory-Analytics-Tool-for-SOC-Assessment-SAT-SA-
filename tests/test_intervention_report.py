from datetime import datetime, timedelta, timezone

from satsa.evidence.package import EvidencePackage
from satsa.ocel.model import EPOCH, OCEL, Event, Obj, ObjectAttributeValue, Relationship
from satsa.reporting.intervention_report import build_intervention_report

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _analyst(aid, tier):
    return Obj(aid, "Analyst", (ObjectAttributeValue("tier", tier, EPOCH),), ())


def _reassign_event(case_id, target, minute):
    return Event(f"R_{case_id}_{minute}", "REASSIGN", T0 + timedelta(minutes=minute), (),
                 (Relationship(case_id, "reassignment_for_case"), Relationship(target, "reassigned_to")))


def _case(case_id, analyst_id):
    return Obj(case_id, "Case", (), (Relationship(analyst_id, "current_assignee"),))


def _mixed_ocel():
    ocel = OCEL()
    ocel.objects = [_analyst("ANL_S", "SENIOR"), _analyst("ANL_J", "JUNIOR")]
    cases = [("C1", "ANL_S", False), ("C2", "ANL_S", False), ("C3", "ANL_J", True),
              ("C4", "ANL_J", True), ("C5", "ANL_S", True), ("C6", "ANL_J", False)]
    for case_id, analyst_id, looped in cases:
        ocel.objects.append(_case(case_id, analyst_id))
        if looped:
            ocel.events += [_reassign_event(case_id, "ANL_S", 0), _reassign_event(case_id, "ANL_J", 10),
                             _reassign_event(case_id, "ANL_S", 20)]
    return ocel


def _concern(finding_id, finding_type, verdict=None):
    return EvidencePackage(
        finding_id=finding_id, finding_type=finding_type, capability="Operational Discipline",
        authority="EXPECTED", rule_id=None, rule_version=None, anomaly_score=1.0, finding_score=1.0,
        concern_score=0.35, confidence=1.0, evidence_quality="HIGH", estimated_review_cost_minutes=10.0,
        affected_objects=["C3"], verdict=verdict,
    )


def test_unverdicted_finding_still_gets_a_preliminary_signal():
    """The whole point of the two-tier redesign: an entity-wide signal is real and
    computable regardless of verdict status — it must not sit silent until someone
    manually confirms one specific finding."""
    report = build_intervention_report("CSE_X", _mixed_ocel(), [_concern("F1", "REASSIGNMENT_LOOP")])
    assert "Preliminary signals" in report
    assert "Confirmed interventions" not in report
    assert "F1" in report  # the "why" bullet names the actual finding behind the signal


def test_confirmed_reassignment_loop_with_enough_data_produces_a_real_opportunity():
    concerns = [_concern("F1", "REASSIGNMENT_LOOP", verdict="TRUE_SUPERVISORY_FINDING")]
    report = build_intervention_report("CSE_X", _mixed_ocel(), concerns)
    assert "Confirmed interventions" in report
    assert "F1" in report
    assert "Robustness value" in report
    assert ("ACT" in report) or ("INVESTIGATE" in report)


def test_a_different_supported_finding_type_also_gets_a_preliminary_signal():
    concerns = [_concern("F3", "ESCALATION_SLA_VIOLATION")]
    report = build_intervention_report("CSE_X", _mixed_ocel(), concerns)
    assert "Preliminary signals" in report
    assert "Escalation Sla Violation" in report
    assert "F3" in report


def test_truly_unsupported_finding_type_is_listed_not_silently_dropped():
    concerns = [_concern("F2", "FAST_CLOSE_OUTLIER", verdict="TRUE_SUPERVISORY_FINDING")]
    report = build_intervention_report("CSE_X", _mixed_ocel(), concerns)
    assert "No estimand available yet" in report
    assert "FAST_CLOSE_OUTLIER" in report


def test_report_never_mutates_the_input_concerns():
    concerns = [_concern("F1", "REASSIGNMENT_LOOP", verdict="TRUE_SUPERVISORY_FINDING")]
    before = concerns[0].concern_score
    build_intervention_report("CSE_X", _mixed_ocel(), concerns)
    assert concerns[0].concern_score == before
