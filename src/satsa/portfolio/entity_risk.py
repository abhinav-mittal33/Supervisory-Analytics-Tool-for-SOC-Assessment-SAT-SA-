"""Entity-level supervisory risk indicator (PS Functional Requirement 9) — combines
cross-CSE peer-comparison results (`peer_comparison.py`) into one composite score per
CSE, reusing the exact severity/materiality weights `moat1/fusion.py` already defines
for per-finding scoring, rather than inventing a second weighting scheme.

`ENTITY_RISK_TIER_THRESHOLDS` are documented engineering constants pending real
calibration data — the same honesty posture `sampling/cost_model.py`'s coefficients
already hold themselves to. Not fit to any data; a placeholder until real portfolio
history exists to calibrate against.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from satsa.moat1.fusion import AUTHORITY_SEVERITY_WEIGHT, CAPABILITY_MATERIALITY
from satsa.moat1.negative_space import NegativeSpaceFinding
from satsa.okf.rules import ENR_PREC_001, ESC_CRIT_001
from satsa.portfolio.entity_metrics import CORE_FINDING_TYPES
from satsa.portfolio.peer_comparison import compare_all_entities

# (capability, authority) per finding_type — matches the literal values moat1/fusion.py
# already assigns each finding_type at creation time (REASSIGNMENT_LOOP's are hardcoded
# there; ESCALATION_SLA_VIOLATION/MISSING_ENRICHMENT come from their OKF rule objects).
FINDING_TYPE_META = {
    "REASSIGNMENT_LOOP": ("Operational Discipline", "EXPECTED"),
    "ESCALATION_SLA_VIOLATION": (ESC_CRIT_001.capability, ESC_CRIT_001.authority),
    "MISSING_ENRICHMENT": (ENR_PREC_001.capability, ENR_PREC_001.authority),
}

# Ascending (score_at_or_above, tier) cutoffs; a score clearing every cutoff -> CRITICAL.
# Calibrated to the formula's own realistic range (abs(z) * materiality[0.3-1.0] *
# authority_weight[0.1-1.0] per flagged finding_type, summed across at most 3 core
# finding types) — NOT calibrated against real portfolio history, which doesn't
# exist yet. Revisit the moment real multi-CSE data is available.
ENTITY_RISK_TIER_THRESHOLDS = [(0.0, "LOW"), (0.7, "MEDIUM"), (1.5, "HIGH")]


@dataclass(frozen=True)
class EntityRiskIndicator:
    cse_id: str
    entity_risk_score: float
    entity_risk_tier: str
    per_finding_type: dict[str, NegativeSpaceFinding] = field(default_factory=dict)


def _tier(score: float) -> str:
    tier = "LOW"
    for threshold, name in ENTITY_RISK_TIER_THRESHOLDS:
        if score >= threshold:
            tier = name
        else:
            break
    else:
        tier = "CRITICAL"  # cleared every cutoff, including the highest
    return tier


def compute_entity_risk_indicators(datasets, finding_types: tuple[str, ...] = CORE_FINDING_TYPES) -> list[EntityRiskIndicator]:
    comparisons = compare_all_entities(datasets, finding_types)

    indicators = []
    for cse_id in datasets:
        score = 0.0
        per_type: dict[str, NegativeSpaceFinding] = {}
        for ft in finding_types:
            finding = comparisons[ft][cse_id]
            per_type[ft] = finding
            if finding.flagged:
                capability, authority = FINDING_TYPE_META[ft]
                score += abs(finding.z_score) * CAPABILITY_MATERIALITY.get(capability, 0.5) * AUTHORITY_SEVERITY_WEIGHT[authority]
        indicators.append(EntityRiskIndicator(cse_id=cse_id, entity_risk_score=score, entity_risk_tier=_tier(score), per_finding_type=per_type))
    return sorted(indicators, key=lambda i: -i.entity_risk_score)
