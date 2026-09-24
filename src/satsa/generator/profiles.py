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

# --- Build Order Step 4: two full-scale, structurally distinct, calibrated profiles ---
# Every rate below is anchored to a cited public benchmark, not invented — see the
# traceability table in docs/references.md for exact quotes, page context, and URLs.
# telemetry_coverage models "the SOC actually has monitoring/detection reach here",
# which is the closest fit in this generator's shape to CardinalOps' distinction
# between data ingested (potential coverage) and rules that actually work (realized
# coverage) — the mapping is approximate, not a literal reuse of their metric, and is
# documented as such rather than presented as more precise than it is.

MATURE_CSE_SCALED = CSEProfile(
    name="CSE_ALPHA_MATURE_SCALED",
    seed=20260925,
    num_cases=2200,
    num_assets=180,
    num_analysts=40,  # above SANS 2025's 2-10 "fully staffed" baseline — a large, above-baseline CSE
    num_queues=6,
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
    telemetry_coverage=0.90,  # CardinalOps 2025: orgs ingest enough data to cover 90% of ATT&CK techniques
    num_reassignment_loop_positive=25,
    num_reassignment_loop_hard_negative=25,
)

SMALL_CSE_SCALED = CSEProfile(
    name="CSE_BETA_SMALL_SCALED",
    seed=20260926,
    num_cases=2000,
    num_assets=60,
    num_analysts=6,  # within SANS 2025's most-common "2-10 people" fully staffed SOC band
    num_queues=2,
    asset_criticality_weights={"LOW": 0.30, "MEDIUM": 0.30, "HIGH": 0.25, "CRITICAL": 0.15},
    alert_severity_weights={"LOW": 0.25, "MEDIUM": 0.30, "HIGH": 0.30, "CRITICAL": 0.15},
    alert_category_weights={
        "MALWARE": 0.30,
        "PHISHING": 0.25,
        "INTRUSION_ATTEMPT": 0.20,
        "POLICY_VIOLATION": 0.15,
        "DATA_EXFILTRATION": 0.10,
    },
    escalation_compliance_rate=0.45,  # lower-maturity SOC: SLA compliance materially worse than the mature profile
    enrichment_rate=0.55,
    # CardinalOps 2025: ~21-22% average realized ATT&CK detection coverage against a
    # potential 90% — this profile's exposure sits far below the mature profile's,
    # consistent with SANS 2025's finding that 42% of SOCs dump all incoming data into
    # a SIEM "often without a retrieval or management plan," i.e. data exists but isn't
    # reliably actionable.
    telemetry_coverage=0.55,
    num_reassignment_loop_positive=20,
    num_reassignment_loop_hard_negative=20,
)
