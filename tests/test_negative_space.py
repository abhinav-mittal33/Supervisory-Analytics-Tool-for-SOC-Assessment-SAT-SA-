"""Build Order Step 7 — exposure-adjusted negative space (Section 9.4)."""
import numpy as np
import pytest

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_SCALED
from satsa.moat1.negative_space import (
    MIN_PEER_GROUP_SIZE,
    PeerGroupObservation,
    detect_negative_space,
)
from satsa.okf import compiler, rules
from satsa.ocel import sqlite_io


def test_pooled_rate_recovers_true_rate_when_all_groups_share_it():
    rng = np.random.default_rng(42)
    true_rate = 0.8
    observations = [
        PeerGroupObservation(f"G{i}", exposure=200, observed=int(rng.binomial(200, true_rate)))
        for i in range(8)
    ]
    findings = detect_negative_space(observations)
    for f in findings:
        assert f.abstain_reason is None
        assert abs(f.expected - true_rate * f.exposure) < 15  # loose tolerance, still a real check
        assert f.expected_ci_low <= f.expected <= f.expected_ci_high


def test_shrinkage_pulls_small_group_toward_pooled_rate():
    # 7 large groups at rate ~0.9, one small group with a raw rate far below everyone
    # else purely by chance (2 out of 3) — shrinkage should pull its estimate up
    # toward the pooled rate rather than trusting the raw 2/3 = 0.667 ratio.
    large_groups = [PeerGroupObservation(f"L{i}", exposure=500, observed=450) for i in range(7)]
    small_group = PeerGroupObservation("SMALL", exposure=3, observed=2)
    findings = detect_negative_space(large_groups + [small_group])

    small_finding = next(f for f in findings if f.group_id == "SMALL")
    assert small_finding.shrunk is True
    raw_rate = small_group.observed / small_group.exposure
    shrunk_rate = small_finding.expected / small_finding.exposure
    pooled_rate = 450 / 500
    assert abs(shrunk_rate - pooled_rate) < abs(raw_rate - pooled_rate)


def test_abstains_on_insufficient_evidence_and_exposure():
    single = detect_negative_space([PeerGroupObservation("ONLY", exposure=100, observed=90)])
    assert single[0].abstain_reason == "INSUFFICIENT_EVIDENCE"

    with_zero_exposure = detect_negative_space(
        [
            PeerGroupObservation("A", exposure=100, observed=90),
            PeerGroupObservation("C", exposure=100, observed=85),
            PeerGroupObservation("B", exposure=0, observed=0),
        ]
    )
    zero_finding = next(f for f in with_zero_exposure if f.group_id == "B")
    assert zero_finding.abstain_reason == "INSUFFICIENT_EXPOSURE"
    assert next(f for f in with_zero_exposure if f.group_id == "A").abstain_reason is None


def test_two_point_all_zero_observed_abstains_instead_of_crashing():
    """Regression: exactly 2 peer groups, BOTH with observed=0 (e.g. a two-cycle
    trend comparison where every case was flagged in both cycles — CSE_D's
    REASSIGNMENT_LOOP rate never moved off 100%) sends the Poisson GLM's deviance
    function a first guess of nan, which statsmodels raises as a ValueError, not
    just a warning — this crashed the whole Streamlit page in production before
    being caught here. Must abstain, never propagate the exception."""
    findings = detect_negative_space([
        PeerGroupObservation("prior", exposure=10, observed=0),
        PeerGroupObservation("current", exposure=10, observed=0),
    ])
    assert all(f.abstain_reason == "INSUFFICIENT_EVIDENCE" for f in findings)


def _queue_escalation_observations(ocel, esc_violations: set[str]) -> list[PeerGroupObservation]:
    case_to_queue = {}
    for o in ocel.objects:
        if o.type != "Case":
            continue
        for r in o.relationships:
            if r.qualifier == "current_queue":
                case_to_queue[o.id] = r.target_id

    duty_cases_by_queue: dict[str, list[str]] = {}
    for o in ocel.objects:
        if o.type == "Case" and o.id in case_to_queue:
            duty_cases_by_queue.setdefault(case_to_queue[o.id], []).append(o.id)

    return [
        PeerGroupObservation(
            group_id=queue_id,
            exposure=len(case_ids),
            observed=len([c for c in case_ids if c not in esc_violations]),
        )
        for queue_id, case_ids in duty_cases_by_queue.items()
    ]


def test_end_to_end_against_generated_data_and_okf_violations(tmp_path):
    ocel, _ = generate(MATURE_CSE_SCALED)
    sqlite_path = str(tmp_path / "negspace_test.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    esc_violations = {v.case_id for v in compiler.evaluate_rule(conn, rules.ESC_CRIT_001)}

    # ESC-CRIT-001 only fires for cases with a duty (severity=CRITICAL, asset HIGH/CRITICAL);
    # negative space here is scoped to the whole Case population per queue, which
    # includes non-duty cases too — observed = "not an ESC-CRIT-001 violation" is a
    # reasonable proxy across the full population since non-duty cases never violate it.
    observations = _queue_escalation_observations(ocel, esc_violations)
    assert observations, "no queues found — test is vacuous"

    findings = detect_negative_space(observations)
    assert len(findings) == len(observations)
    assert sum(f.exposure for f in findings) == sum(o.exposure for o in observations)
    # At full scale each queue should clear the shrinkage threshold.
    assert all(o.exposure >= MIN_PEER_GROUP_SIZE for o in observations)
    assert not any(f.shrunk for f in findings)
