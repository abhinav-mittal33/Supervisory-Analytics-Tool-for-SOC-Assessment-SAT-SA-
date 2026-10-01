"""PS illustrative use-case ix: investigation/escalation workload inconsistent with
expected activity level. Two tiers, same rigor as the other Phase C detectors
(tests/test_detector_*.py): raw-extraction correctness, then the two-sided
negative-space check (planted low, planted high, matched hard-negative, boundary).

No Gate-tested generator profile's natural variance crosses the |z|>=2.0 threshold
(measured directly — max|z|=1.81 across MATURE_CSE_DEV/MATURE_CSE_SCALED/
SMALL_CSE_SCALED, see docs/assumptions.md entry 019), so unlike
tests/test_fusion_phase_c_detectors.py's generator-based wiring test, the fuse()
wiring test here uses a hand-built OCEL with a deliberately planted skew — the
correct substitute per that same honesty standard, not a weaker test.
"""
from datetime import datetime, timezone

from satsa.moat1.fusion import fuse
from satsa.moat1.negative_space import PeerGroupObservation, detect_negative_space
from satsa.moat1.structural import analyst_investigation_counts, queue_escalation_counts
from satsa.ocel import sqlite_io
from satsa.ocel.model import EPOCH, OCEL, AttributeDef, Event, Obj, ObjectAttributeValue, Relationship, TypeDef
from satsa.okf import compiler

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _analyst(aid):
    return Obj(aid, "Analyst", (), ())


def _queue(qid):
    return Obj(qid, "Queue", (), ())


def _case_assigned_to(case_id, analyst_id):
    return Obj(case_id, "Case", (), (Relationship(analyst_id, "current_assignee"),))


def _case_in_queue(case_id, queue_id):
    return Obj(case_id, "Case", (), (Relationship(queue_id, "current_queue"),))


def _investigate_event(event_id, case_id, analyst_id):
    return Event(event_id, "INVESTIGATE", T0, (),
                 (Relationship(case_id, "investigate_for_case"), Relationship(analyst_id, "investigated_by")))


def _escalate_event(event_id, case_id):
    return Event(event_id, "ESCALATE", T0, (), (Relationship(case_id, "escalation_for_case"),))


# --- raw extraction (structural.py) ---

def test_analyst_investigation_counts_counts_assigned_cases_and_investigations():
    ocel = OCEL()
    ocel.objects = [_analyst("ANL1"), _case_assigned_to("C1", "ANL1"), _case_assigned_to("C2", "ANL1")]
    ocel.events = [_investigate_event("INV1", "C1", "ANL1")]
    counts = {aid: (exposure, observed) for aid, exposure, observed in analyst_investigation_counts(ocel)}
    assert counts["ANL1"] == (2, 1)


def test_analyst_with_no_cases_still_appears_with_zero_counts():
    ocel = OCEL()
    ocel.objects = [_analyst("ANL_IDLE")]
    ocel.events = []
    counts = {aid: (exposure, observed) for aid, exposure, observed in analyst_investigation_counts(ocel)}
    assert counts["ANL_IDLE"] == (0, 0)


def test_queue_escalation_counts_resolves_case_to_its_current_queue():
    ocel = OCEL()
    ocel.objects = [_queue("Q1"), _case_in_queue("C1", "Q1"), _case_in_queue("C2", "Q1")]
    ocel.events = [_escalate_event("ESC1", "C1")]
    counts = {qid: (exposure, observed) for qid, exposure, observed in queue_escalation_counts(ocel)}
    assert counts["Q1"] == (2, 1)


# --- two-sided negative-space check (the statistical layer fusion.py reuses) ---

def _peer_analysts(n=10, exposure=20, observed=10):
    return [PeerGroupObservation(f"ANL_PEER{i}", exposure, observed) for i in range(n)]


def test_analyst_investigating_far_fewer_cases_than_peers_is_flagged_low():
    observations = _peer_analysts() + [PeerGroupObservation("ANL_LOW", 20, 2)]
    f = {x.group_id: x for x in detect_negative_space(observations)}["ANL_LOW"]
    assert f.abstain_reason is None
    assert f.z_score <= -2.0


def test_analyst_investigating_far_more_cases_than_peers_is_flagged_high():
    observations = _peer_analysts() + [PeerGroupObservation("ANL_HIGH", 20, 18)]
    f = {x.group_id: x for x in detect_negative_space(observations)}["ANL_HIGH"]
    assert f.abstain_reason is None
    assert f.z_score >= 2.0


def test_analyst_matching_peer_rate_is_the_matched_hard_negative():
    observations = _peer_analysts() + [PeerGroupObservation("ANL_NORMAL", 20, 10)]
    f = {x.group_id: x for x in detect_negative_space(observations)}["ANL_NORMAL"]
    assert f.abstain_reason is None
    assert abs(f.z_score) < 2.0


def test_zero_exposure_analyst_abstains_instead_of_being_flagged():
    observations = _peer_analysts() + [PeerGroupObservation("ANL_UNASSIGNED", 0, 0)]
    f = {x.group_id: x for x in detect_negative_space(observations)}["ANL_UNASSIGNED"]
    assert f.abstain_reason == "INSUFFICIENT_EXPOSURE"


# --- real fuse() wiring, hand-built OCEL with a planted skew (see module docstring
# for why this replaces the generator-based pattern used elsewhere in this test suite) ---

def _case_assigned_to_with_alert(case_id, analyst_id):
    # okf/compiler.py's case_context view only builds when both Alert and Asset
    # object types are present (it's a generic OKF engine, not SOC-specific) — fuse()
    # always evaluates the OKF rules regardless, so even this non-OKF-focused fixture
    # needs a minimal, deliberately LOW/LOW (non-CRITICAL) alert+asset per case so
    # that view exists and ESC_CRIT_001 cleanly finds zero matching cases rather than
    # the view being absent entirely.
    return Obj(case_id, "Case", (), (
        Relationship(analyst_id, "current_assignee"),
        Relationship("AL_SHARED", "case_for_alert"),
    ))


def _build_workload_ocel():
    ocel = OCEL()
    objects = [
        Obj("AL_SHARED", "Alert", (ObjectAttributeValue("severity", "LOW", EPOCH),),
            (Relationship("AST_SHARED", "raised_on_asset"),)),
        Obj("AST_SHARED", "Asset", (ObjectAttributeValue("criticality", "LOW", EPOCH),), ()),
    ]
    events = []
    # 10 peer analysts: 20 assigned cases each, 10 investigated (rate 0.5) -> pooled baseline.
    for i in range(10):
        aid = f"ANL_PEER{i}"
        objects.append(_analyst(aid))
        for c in range(20):
            case_id = f"C_{aid}_{c}"
            objects.append(_case_assigned_to_with_alert(case_id, aid))
            if c < 10:
                events.append(_investigate_event(f"INV_{case_id}", case_id, aid))
    # one analyst investigates far fewer of their own cases than peers (2 of 20).
    objects.append(_analyst("ANL_LOW"))
    for c in range(20):
        case_id = f"C_ANL_LOW_{c}"
        objects.append(_case_assigned_to_with_alert(case_id, "ANL_LOW"))
        if c < 2:
            events.append(_investigate_event(f"INV_{case_id}", case_id, "ANL_LOW"))
    ocel.objects = objects
    ocel.events = events
    ocel.object_types = [
        TypeDef("Analyst"), TypeDef("Case"),
        TypeDef("Alert", (AttributeDef("severity", "string"),)),
        TypeDef("Asset", (AttributeDef("criticality", "string"),)),
    ]
    ocel.event_types = [TypeDef("INVESTIGATE")]
    return ocel


def test_fuse_produces_a_correctly_labeled_investigation_workload_finding(tmp_path):
    ocel = _build_workload_ocel()
    sqlite_path = str(tmp_path / "workload.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    concerns = fuse(ocel, conn).concerns

    workload_concerns = [c for c in concerns if c.finding_type == "INVESTIGATION_WORKLOAD_INCONSISTENT"]
    assert workload_concerns, "planted under-active analyst did not produce a workload finding"
    c = workload_concerns[0]
    assert c.affected_objects == ["ANL_LOW"]
    assert c.capability == "Investigation"
    assert c.authority == "PEER_NORMAL"
    assert len(c.supporting_cases) == 20
