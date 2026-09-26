"""Gate 5 — Temporal axis, two-cycle comparison (docs/validation_plan.md).
Previously deferred as optional; revived because PS req 16 ("trend analysis across
time periods") names it directly. STOP condition (spec Section 13, unchanged):
correctly distinguishes VERIFIED_IMPROVEMENT / POTENTIAL_DISPLACEMENT / REGRESSED /
INSUFFICIENT_EVIDENCE — checked here against hand-built scenarios, not just "runs".
"""
from satsa.moat1.negative_space import PeerGroupObservation
from satsa.temporal.cycles import TrendClassification, classify_trend


def test_verified_improvement_no_proxy_given():
    # Larger exposure than the other scenarios, deliberately — a two-point pooled
    # rate needs enough volume for the same relative rate shift to clear the z
    # threshold (the pooled baseline is itself built from these same two points).
    prior = PeerGroupObservation(group_id="cycle1", exposure=1000, observed=700)   # 30% problem rate
    current = PeerGroupObservation(group_id="cycle2", exposure=1000, observed=950)  # 5% problem rate
    assert classify_trend(prior, current) == TrendClassification.VERIFIED_IMPROVEMENT


def test_regressed():
    prior = PeerGroupObservation(group_id="cycle1", exposure=1000, observed=950)
    current = PeerGroupObservation(group_id="cycle2", exposure=1000, observed=600)
    assert classify_trend(prior, current) == TrendClassification.REGRESSED


def test_potential_displacement_when_a_proxy_metric_simultaneously_worsens():
    prior = PeerGroupObservation(group_id="cycle1", exposure=1000, observed=700)
    current = PeerGroupObservation(group_id="cycle2", exposure=1000, observed=950)
    proxy_prior = PeerGroupObservation(group_id="cycle1", exposure=1000, observed=900)
    proxy_current = PeerGroupObservation(group_id="cycle2", exposure=1000, observed=500)
    assert classify_trend(prior, current, proxy_prior, proxy_current) == TrendClassification.POTENTIAL_DISPLACEMENT


def test_insufficient_evidence_below_min_peer_group_size():
    prior = PeerGroupObservation(group_id="cycle1", exposure=5, observed=4)
    current = PeerGroupObservation(group_id="cycle2", exposure=5, observed=5)
    assert classify_trend(prior, current) == TrendClassification.INSUFFICIENT_EVIDENCE


def test_insufficient_evidence_when_rates_barely_move():
    prior = PeerGroupObservation(group_id="cycle1", exposure=100, observed=90)
    current = PeerGroupObservation(group_id="cycle2", exposure=100, observed=91)
    assert classify_trend(prior, current) == TrendClassification.INSUFFICIENT_EVIDENCE
