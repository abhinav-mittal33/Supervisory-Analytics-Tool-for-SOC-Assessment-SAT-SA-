"""Examiner review cost model (build spec Section 10.2).

cost_minutes = base_time + per_alert_time*num_alerts_linked
             + evidence_review_time*evidence_volume
             + missing_data_penalty (if evidence incomplete)
             * complexity_factor(authority)

These are engineering estimates until real examiner timing data calibrates them
(Section 10.2's own words) — the coefficients are configurable and the examiner can
override the estimate in the UI once one exists (Section 17), with the correction
logged as feedback, not silently discarded.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Complexity multiplier by authority class — a MANDATORY finding usually carries more
# scrutiny/documentation burden for the examiner than an OPTIONAL one.
_DEFAULT_COMPLEXITY_WEIGHT = {
    "MANDATORY": 1.5,
    "EXPECTED": 1.2,
    "PEER_NORMAL": 1.0,
    "OPTIONAL": 0.8,
    "UNKNOWN": 1.0,
}


@dataclass(frozen=True)
class CostCoefficients:
    base_time: float = 15.0
    per_alert_time: float = 5.0
    evidence_review_time: float = 2.0
    missing_data_penalty: float = 20.0
    complexity_weight: dict = field(default_factory=lambda: dict(_DEFAULT_COMPLEXITY_WEIGHT))


DEFAULT_COEFFICIENTS = CostCoefficients()


def estimate_review_cost_minutes(
    *,
    evidence_volume: int,
    authority: str,
    evidence_quality: str,
    num_alerts_linked: int = 1,
    coefficients: CostCoefficients = DEFAULT_COEFFICIENTS,
) -> float:
    cost = coefficients.base_time + coefficients.per_alert_time * num_alerts_linked
    cost += coefficients.evidence_review_time * evidence_volume
    if evidence_quality != "HIGH":
        cost += coefficients.missing_data_penalty
    complexity = coefficients.complexity_weight.get(authority, 1.0)
    return cost * complexity
