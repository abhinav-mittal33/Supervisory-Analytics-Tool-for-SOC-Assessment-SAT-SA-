"""Two-cycle temporal comparison (build spec Section 13, scoped-down contingency
version — previously deferred as optional Gate 5, now in scope because PS
Functional Requirement 16, "trend analysis across time periods," names it directly).

Reuses `moat1/negative_space.py::detect_negative_space` unmodified — a two-cycle
comparison is just peer comparison with `group_id` = cycle label instead of CSE id
or queue id. No new statistical engine.

Categories are the spec's own Section 13 ontology, not invented ones:
VERIFIED_IMPROVEMENT / POTENTIAL_DISPLACEMENT / REGRESSED / INSUFFICIENT_EVIDENCE.
"""
from __future__ import annotations

from enum import Enum

from satsa.moat1.negative_space import MIN_PEER_GROUP_SIZE, PeerGroupObservation, detect_negative_space

Z_TREND_THRESHOLD = 2.0  # same magnitude as negative_space.py's own Z_CONCERN_THRESHOLD


class TrendClassification(Enum):
    VERIFIED_IMPROVEMENT = "VERIFIED_IMPROVEMENT"
    POTENTIAL_DISPLACEMENT = "POTENTIAL_DISPLACEMENT"
    REGRESSED = "REGRESSED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def classify_trend(
    prior: PeerGroupObservation,
    current: PeerGroupObservation,
    proxy_prior: PeerGroupObservation | None = None,
    proxy_current: PeerGroupObservation | None = None,
) -> TrendClassification:
    """`observed` on both `prior`/`current` must follow the same "count of cases
    WITHOUT the problem" polarity `portfolio/entity_metrics.py` already establishes
    for cross-CSE comparison — this is the identical convention, applied across
    cycles instead of across entities.

    `proxy_prior`/`proxy_current` are an optional second, independently-tracked
    metric checked for the spec's own "fixed what's measured, pushed the problem
    elsewhere" concern. This is a documented HEURISTIC (simultaneous opposite
    movement on a plausibly-related metric), not a proof of displacement.
    """
    if prior.exposure < MIN_PEER_GROUP_SIZE or current.exposure < MIN_PEER_GROUP_SIZE:
        return TrendClassification.INSUFFICIENT_EVIDENCE

    findings = {f.group_id: f for f in detect_negative_space([prior, current])}
    current_finding = findings[current.group_id]
    if current_finding.abstain_reason or current_finding.z_score is None:
        return TrendClassification.INSUFFICIENT_EVIDENCE
    if abs(current_finding.z_score) < Z_TREND_THRESHOLD:
        return TrendClassification.INSUFFICIENT_EVIDENCE

    if current_finding.z_score < 0:
        return TrendClassification.REGRESSED

    if proxy_prior is not None and proxy_current is not None:
        proxy_findings = {f.group_id: f for f in detect_negative_space([proxy_prior, proxy_current])}
        proxy_current_finding = proxy_findings[proxy_current.group_id]
        if proxy_current_finding.z_score is not None and proxy_current_finding.z_score <= -Z_TREND_THRESHOLD:
            return TrendClassification.POTENTIAL_DISPLACEMENT

    return TrendClassification.VERIFIED_IMPROVEMENT
