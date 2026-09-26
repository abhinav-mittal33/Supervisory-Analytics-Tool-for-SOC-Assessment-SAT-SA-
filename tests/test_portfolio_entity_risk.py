"""Phase B: cross-CSE peer comparison + entity risk indicator. Brute-force-checked
against a hand-built 4-CSE scenario with one deliberately deviant CSE (same
verification standard Gate 4 used for submodular selection) — not just "runs".
"""
from satsa.moat1.fusion import FusionResult
from satsa.evidence.package import EvidencePackage
from satsa.ocel.model import OCEL, Obj
from satsa.portfolio.entity_metrics import build_peer_observations, case_count
from satsa.portfolio.entity_risk import compute_entity_risk_indicators
from satsa.portfolio.peer_comparison import compare_entities


def _ocel_with_n_cases(n: int) -> OCEL:
    ocel = OCEL()
    ocel.objects = [Obj(f"CASE{i:03d}", "Case", (), ()) for i in range(n)]
    return ocel


def _concern(case_id: str, finding_type: str) -> EvidencePackage:
    return EvidencePackage(
        finding_id=f"FIND_{case_id}_{finding_type}", finding_type=finding_type,
        capability="Operational Discipline", authority="EXPECTED", rule_id=None, rule_version=None,
        anomaly_score=1.0, finding_score=1.0, concern_score=1.0, confidence=1.0,
        evidence_quality="HIGH", estimated_review_cost_minutes=10.0, affected_objects=[case_id],
    )


def test_case_count_counts_only_case_objects():
    ocel = _ocel_with_n_cases(5)
    ocel.objects.append(Obj("ANL001", "Analyst", (), ()))
    assert case_count(ocel) == 5


def test_deviant_cse_gets_flagged_against_its_peers():
    # 3 "quiet" CSEs at a low, consistent reassignment-loop rate, 1 "deviant" CSE
    # with a dramatically higher rate — a real peer-comparison signal, brute-force
    # checkable: the deviant CSE's observed count is far above what the other three's
    # pooled rate would predict for its exposure.
    datasets = {}
    for cse in ("CSE_A", "CSE_B", "CSE_C"):
        ocel = _ocel_with_n_cases(100)
        concerns = [_concern(f"CASE{i:03d}", "REASSIGNMENT_LOOP") for i in range(2)]  # 2/100 quiet rate
        datasets[cse] = (ocel, FusionResult(concerns=concerns, suppressed=[]))

    deviant_ocel = _ocel_with_n_cases(100)
    deviant_concerns = [_concern(f"CASE{i:03d}", "REASSIGNMENT_LOOP") for i in range(40)]  # 40/100 — way above peers
    datasets["CSE_DEVIANT"] = (deviant_ocel, FusionResult(concerns=deviant_concerns, suppressed=[]))

    comparison = compare_entities(datasets, "REASSIGNMENT_LOOP")
    assert comparison["CSE_DEVIANT"].flagged
    assert not comparison["CSE_A"].flagged
    # observed here is "cases WITHOUT the problem" (see entity_metrics.py docstring) —
    # the deviant CSE has far fewer of those than its peers.
    assert comparison["CSE_DEVIANT"].observed < comparison["CSE_A"].observed


def test_deviant_cse_ranks_first_by_entity_risk_score():
    datasets = {}
    for cse in ("CSE_A", "CSE_B", "CSE_C"):
        ocel = _ocel_with_n_cases(100)
        concerns = [_concern(f"CASE{i:03d}", "REASSIGNMENT_LOOP") for i in range(2)]
        datasets[cse] = (ocel, FusionResult(concerns=concerns, suppressed=[]))
    deviant_ocel = _ocel_with_n_cases(100)
    deviant_concerns = [_concern(f"CASE{i:03d}", "REASSIGNMENT_LOOP") for i in range(40)]
    datasets["CSE_DEVIANT"] = (deviant_ocel, FusionResult(concerns=deviant_concerns, suppressed=[]))

    indicators = compute_entity_risk_indicators(datasets, finding_types=("REASSIGNMENT_LOOP",))
    assert indicators[0].cse_id == "CSE_DEVIANT"
    assert indicators[0].entity_risk_tier in ("MEDIUM", "HIGH", "CRITICAL")
    assert indicators[0].entity_risk_score > indicators[-1].entity_risk_score


def test_uniform_peers_all_get_low_tier_no_findings_flagged():
    datasets = {}
    for cse in ("CSE_A", "CSE_B", "CSE_C", "CSE_D"):
        ocel = _ocel_with_n_cases(50)
        concerns = [_concern(f"CASE{i:03d}", "REASSIGNMENT_LOOP") for i in range(3)]
        datasets[cse] = (ocel, FusionResult(concerns=concerns, suppressed=[]))

    indicators = compute_entity_risk_indicators(datasets, finding_types=("REASSIGNMENT_LOOP",))
    assert all(i.entity_risk_tier == "LOW" for i in indicators)


def test_build_peer_observations_reuses_negative_space_dataclass_directly():
    ocel = _ocel_with_n_cases(10)
    datasets = {"CSE_X": (ocel, FusionResult(concerns=[], suppressed=[]))}
    obs = build_peer_observations(datasets, "REASSIGNMENT_LOOP")
    assert obs[0].group_id == "CSE_X"
    assert obs[0].exposure == 10
    assert obs[0].observed == 10  # zero concerns -> every case counts as "without the problem"
