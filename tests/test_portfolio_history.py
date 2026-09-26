from satsa.evidence.package import EvidencePackage
from satsa.moat1.fusion import FusionResult
from satsa.ocel.model import OCEL, AttributeDef, Event, Obj, Relationship, TypeDef
from satsa.portfolio import history as history_mod
from satsa.temporal.cycles import TrendClassification, classify_trend
from datetime import datetime, timezone


def _ocel_with_n_cases(n: int) -> OCEL:
    ocel = OCEL()
    ocel.object_types = [
        TypeDef("Case", ()),
        TypeDef("Alert", (AttributeDef("severity", "string"), AttributeDef("category", "string"))),
        TypeDef("Asset", (AttributeDef("criticality", "string"), AttributeDef("asset_type", "string"))),
        TypeDef("Analyst", (AttributeDef("tier", "string"),)),
        TypeDef("Queue", (AttributeDef("name", "string"),)),
    ]
    ocel.event_types = [TypeDef("CLOSE", ())]
    ocel.objects = [Obj(f"CASE{i:03d}", "Case", (), ()) for i in range(n)]
    ocel.events = [
        Event(f"E{i:03d}", "CLOSE", datetime(2026, 1, 1, tzinfo=timezone.utc), (), (Relationship(f"CASE{i:03d}", "close_for_case"),))
        for i in range(n)
    ]
    return ocel


def _concern(case_id: str, finding_type: str) -> EvidencePackage:
    return EvidencePackage(
        finding_id=f"F_{case_id}_{finding_type}", finding_type=finding_type, capability="Operational Discipline",
        authority="EXPECTED", rule_id=None, rule_version=None, anomaly_score=1.0, finding_score=1.0,
        concern_score=1.0, confidence=1.0, evidence_quality="HIGH", estimated_review_cost_minutes=10.0,
        affected_objects=[case_id],
    )


def test_record_and_list_submissions(tmp_path, monkeypatch):
    monkeypatch.setattr(history_mod, "HISTORY_DIR", tmp_path)
    ocel = _ocel_with_n_cases(20)
    result = FusionResult(concerns=[_concern("CASE000", "REASSIGNMENT_LOOP")], suppressed=[])
    history_mod.record_submission("CSE_TEST", ocel, result)
    records = history_mod.list_submissions("CSE_TEST")
    assert len(records) == 1
    assert records[0].case_count == 20
    assert records[0].per_finding_type["REASSIGNMENT_LOOP"]["flagged_count"] == 1


def test_latest_two_returns_none_prior_when_only_one_submission(tmp_path, monkeypatch):
    monkeypatch.setattr(history_mod, "HISTORY_DIR", tmp_path)
    ocel = _ocel_with_n_cases(10)
    result = FusionResult(concerns=[], suppressed=[])
    history_mod.record_submission("CSE_TEST", ocel, result)
    prior, current = history_mod.latest_two("CSE_TEST")
    assert prior is None
    assert current is not None


def test_seed_demo_history_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(history_mod, "HISTORY_DIR", tmp_path)
    ocel = _ocel_with_n_cases(15)
    result = FusionResult(concerns=[_concern(f"CASE{i:03d}", "REASSIGNMENT_LOOP") for i in range(5)], suppressed=[])
    history_mod.seed_demo_history("CSE_SEED", ocel, result)
    assert len(history_mod.list_submissions("CSE_SEED")) == 2
    history_mod.seed_demo_history("CSE_SEED", ocel, result)  # second call must not add more
    assert len(history_mod.list_submissions("CSE_SEED")) == 2


def test_seeded_history_produces_a_real_trend_classification(tmp_path, monkeypatch):
    monkeypatch.setattr(history_mod, "HISTORY_DIR", tmp_path)
    ocel = _ocel_with_n_cases(30)
    result = FusionResult(concerns=[], suppressed=[])  # zero flagged now
    history_mod.seed_demo_history("CSE_SEED2", ocel, result)
    prior, current = history_mod.latest_two("CSE_SEED2")
    assert prior is not None and current is not None
    prior_obs, current_obs = history_mod.trend_observations(prior, current, "REASSIGNMENT_LOOP")
    classification = classify_trend(prior_obs, current_obs)
    assert classification in (TrendClassification.VERIFIED_IMPROVEMENT, TrendClassification.INSUFFICIENT_EVIDENCE)


def test_load_batch_reloads_the_full_dataset_for_a_real_submission(tmp_path, monkeypatch):
    monkeypatch.setattr(history_mod, "HISTORY_DIR", tmp_path)
    ocel = _ocel_with_n_cases(12)
    result = FusionResult(concerns=[], suppressed=[])
    record = history_mod.record_submission("CSE_TEST", ocel, result)
    loaded = history_mod.load_batch("CSE_TEST", record.submitted_at)
    assert loaded is not None
    loaded_ocel, loaded_result = loaded
    assert len(loaded_ocel.objects) == 12


def test_load_batch_returns_none_for_the_demo_seed_cycle_with_no_real_data(tmp_path, monkeypatch):
    monkeypatch.setattr(history_mod, "HISTORY_DIR", tmp_path)
    ocel = _ocel_with_n_cases(10)
    result = FusionResult(concerns=[], suppressed=[])
    history_mod.seed_demo_history("CSE_SEED3", ocel, result)
    prior, _current = history_mod.latest_two("CSE_SEED3")
    assert history_mod.load_batch("CSE_SEED3", prior.submitted_at) is None
