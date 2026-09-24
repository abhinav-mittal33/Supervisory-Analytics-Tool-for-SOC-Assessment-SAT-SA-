"""CSE profile definitions for the synthetic generator (build spec Section 14).

Every distributional parameter here is a placeholder pending the calibration pass at
Build Order Step 4 (docs/references.md gets the cited-source traceability table then).
Flagging that explicitly rather than presenting these numbers as already calibrated —
Section 14.3 requires citation, not invention, and Step 2 is dev-scale-shape-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CSEProfile:
    name: str
    seed: int
    num_cases: int
    num_assets: int
    num_analysts: int
    num_queues: int
    asset_criticality_weights: dict[str, float]
    alert_severity_weights: dict[str, float]
    alert_category_weights: dict[str, float]
    escalation_compliance_rate: float  # fraction of MANDATORY-escalation cases that meet the SLA
    enrichment_rate: float  # fraction of cases that get an ENRICH event before INVESTIGATE
    telemetry_coverage: float  # fraction of assets that produce alerts at all (exposure)
    num_reassignment_loop_positive: int  # planted pathology count (Section 9.2, Gate 1)
    num_reassignment_loop_hard_negative: int  # matched look-alike (Section 15, Gate 1)


# Dev-scale (Build Order Step 2): shape-validation only, not yet calibrated (see docstring).
MATURE_CSE_DEV = CSEProfile(
    name="CSE_ALPHA_MATURE_DEV",
    seed=20260925,
    num_cases=300,
    num_assets=50,
    num_analysts=15,
    num_queues=4,
    asset_criticality_weights={"LOW": 0.35, "MEDIUM": 0.35, "HIGH": 0.20, "CRITICAL": 0.10},
    alert_severity_weights={"LOW": 0.30, "MEDIUM": 0.35, "HIGH": 0.25, "CRITICAL": 0.10},
    alert_category_weights={
        "MALWARE": 0.30,
        "PHISHING": 0.25,
        "INTRUSION_ATTEMPT": 0.20,
        "POLICY_VIOLATION": 0.15,
        "DATA_EXFILTRATION": 0.10,
    },
    escalation_compliance_rate=0.75,
    enrichment_rate=0.85,
    telemetry_coverage=0.90,
    num_reassignment_loop_positive=6,
    num_reassignment_loop_hard_negative=6,
)
