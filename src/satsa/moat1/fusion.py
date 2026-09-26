"""Anomaly -> Finding -> Concern fusion (Section 5.2) into Evidence Packages
(Section 11) — Build Order Step 8, scored against Gate 2.

Scope for this build: case-level fusion only, over the detectors already gated
(structural.py's reassignment-loop signal, and the OKF compiler's per-case Response/
Precedence/Cardinality violations). Queue-level negative-space and period-level drift
findings are a separate entity/portfolio-level Concern stream, not yet fused into this
per-case pipeline — see docs/assumptions.md entry 006.

Every current detector's anomaly_score and conformance_deviation are binary (the
pattern/rule either matched or the case produces no signal at all) — none of them yet
produce a continuous, calibrated magnitude. That's an honest limitation, not a hidden
one: a genuinely continuous anomaly score is the secondary Isolation-Forest
detector's job (Section 9.3), which isn't required for Gate 2.

The key fusion behavior Gate 2 actually tests: REASSIGN-CARD-001 (a generic,
count-only OKF Cardinality rule) fires on every case with >2 REASSIGN events,
including the matched hard negatives (shift-change justified loops) and the
REASSIGNMENT_CHAIN_NO_LOOP background-noise cases — exactly the false-positive shape
Section 9.1 warns a count-only rule will produce. Fusion suppresses that rule's output
whenever the more specific, genuinely object-centric structural detector has already
ruled on the same case, and logs why — so a coarser rule can't reintroduce a false
positive the finer one correctly excluded.
"""
from __future__ import annotations

from dataclasses import dataclass

import duckdb

from satsa.evidence.package import EvidencePackage, Provenance
from satsa.moat1.negative_space import PeerGroupObservation, detect_negative_space
from satsa.moat1.structural import (
    asset_alert_counts,
    case_open_close_times,
    detect_asset_alert_recurrence,
    detect_fast_close,
    detect_investigation_uniformity,
    detect_reassignment_loops,
)
from satsa.ocel.model import OCEL
from satsa.okf.compiler import evaluate_rule
from satsa.okf.rules import ENR_PREC_001, ESC_CRIT_001, REASSIGN_CARD_001
from satsa.sampling.cost_model import estimate_review_cost_minutes

EVIDENCE_QUALITY_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}
AUTHORITY_SEVERITY_WEIGHT = {"MANDATORY": 1.0, "EXPECTED": 0.7, "PEER_NORMAL": 0.5, "OPTIONAL": 0.3, "UNKNOWN": 0.1}
CAPABILITY_MATERIALITY = {
    "Escalation": 1.0, "Investigation": 0.8, "Operational Discipline": 0.5,
    "Incident Response": 0.9, "Threat Detection": 0.9,
}
HIGH_CRITICALITY_TIERS = {"HIGH", "CRITICAL"}

# Uniform for this build's synthetic, complete-by-construction data — no simulated
# broken/missing records yet (that's the Data Reliability/ABSTAIN gate, Section 5.3,
# not yet built — see docs/assumptions.md entry 006).
DEFAULT_EVIDENCE_QUALITY = "HIGH"


@dataclass(frozen=True)
class FusionResult:
    concerns: list[EvidencePackage]
    suppressed: list[str]  # human-readable audit notes for signals a finer detector overrode


def _case_severity_map(ocel: OCEL) -> dict[str, str]:
    alert_severity = {
        o.id: next((a.value for a in o.attributes if a.name == "severity"), "UNKNOWN")
        for o in ocel.objects if o.type == "Alert"
    }
    case_alert: dict[str, str] = {}
    for o in ocel.objects:
        if o.type == "Case":
            for r in o.relationships:
                if r.qualifier == "case_for_alert":
                    case_alert[o.id] = r.target_id
    return {case_id: alert_severity.get(alert_id, "UNKNOWN") for case_id, alert_id in case_alert.items()}


def _event_ids_for_case(ocel: OCEL, case_id: str, event_type: str | None = None) -> list[str]:
    ids = []
    for e in ocel.events:
        if event_type is not None and e.type != event_type:
            continue
        if any(r.target_id == case_id and r.qualifier.endswith("_for_case") for r in e.relationships):
            ids.append(e.id)
    return ids


def _make_package(
    *, finding_id: str, finding_type: str, capability: str, authority: str,
    rule_id: str | None, rule_version: str | None, primary_id: str, event_ids: list[str],
    assumptions_notes: list[str], cse_id: str | None = None,
    low_confidence_cases: frozenset[str] = frozenset(),
    supporting_cases: list[str] | None = None,
) -> EvidencePackage:
    """primary_id is the affected object's ID — a case_id for the original
    per-case detectors, but an asset_id or analyst_id for the entity-level
    detectors added in Phase C (asset recurrence, telemetry, investigation
    uniformity). low_confidence-case downgrading only ever matches real case_ids,
    so it's a harmless no-op for the non-case finding types."""
    if primary_id in low_confidence_cases:
        evidence_quality = "MEDIUM"
        assumptions_notes = assumptions_notes + [
            "evidence_quality downgraded from HIGH: this case's case_events included an "
            "unrecognized event value during ingestion (docs/assumptions.md entry 011) — "
            "the event trace for this case may be incomplete, not because a value was "
            "guessed, but because it was correctly skipped rather than guessed."
        ]
    else:
        evidence_quality = DEFAULT_EVIDENCE_QUALITY
    anomaly_score = 1.0
    conformance_deviation = 1.0
    finding_score = anomaly_score * conformance_deviation * EVIDENCE_QUALITY_WEIGHT[evidence_quality]
    capability_materiality = CAPABILITY_MATERIALITY.get(capability, 0.5)
    severity_weight = AUTHORITY_SEVERITY_WEIGHT[authority]
    concern_score = finding_score * capability_materiality * severity_weight
    review_cost = estimate_review_cost_minutes(
        evidence_volume=len(event_ids), authority=authority, evidence_quality=evidence_quality
    )

    return EvidencePackage(
        finding_id=finding_id,
        finding_type=finding_type,
        capability=capability,
        authority=authority,
        rule_id=rule_id,
        rule_version=rule_version,
        anomaly_score=anomaly_score,
        finding_score=finding_score,
        concern_score=concern_score,
        confidence=1.0,
        evidence_quality=evidence_quality,
        estimated_review_cost_minutes=review_cost,
        affected_objects=[primary_id],
        supporting_cases=supporting_cases if supporting_cases is not None else [primary_id],
        supporting_events=event_ids,
        assumptions=assumptions_notes,
        provenance=Provenance(
            source_system="satsa-generator",
            source_file="",
            source_record_id=primary_id,
            ingestion_batch_id="",
            ingestion_timestamp="",
            schema_version="1.0",
        ),
        cse_id=cse_id,
    )


def fuse(
    ocel: OCEL, conn: duckdb.DuckDBPyConnection, *,
    cse_id: str | None = None, low_confidence_cases: set[str] | None = None,
) -> FusionResult:
    low_confidence = frozenset(low_confidence_cases or ())
    signals_by_case = {s.case_id: s for s in detect_reassignment_loops(ocel)}
    esc_violations = {v.case_id: v for v in evaluate_rule(conn, ESC_CRIT_001)}
    enr_violations = {v.case_id: v for v in evaluate_rule(conn, ENR_PREC_001)}
    card_violations = {v.case_id: v for v in evaluate_rule(conn, REASSIGN_CARD_001)}

    concerns: list[EvidencePackage] = []
    suppressed: list[str] = []
    finding_counter = 0

    def next_finding_id() -> str:
        nonlocal finding_counter
        finding_counter += 1
        return f"FIND{finding_counter:05d}"

    for case_id, sig in signals_by_case.items():
        if sig.flagged:
            concerns.append(
                _make_package(
                    finding_id=next_finding_id(),
                    finding_type="REASSIGNMENT_LOOP",
                    capability="Operational Discipline",
                    authority="EXPECTED",
                    rule_id=None,
                    rule_version=None,
                    primary_id=case_id,
                    event_ids=_event_ids_for_case(ocel, case_id, "REASSIGN"),
                    assumptions_notes=[
                        f"This case bounced back and forth between {len(set(sig.analyst_sequence))} analysts "
                        f"({', '.join(dict.fromkeys(sig.analyst_sequence))}) {len(sig.analyst_sequence)} times in "
                        "a row, with no documented shift-change reason recorded for any of the handoffs.",
                        f"analyst_sequence={sig.analyst_sequence}",
                    ],
                    cse_id=cse_id, low_confidence_cases=low_confidence,
                )
            )
        elif sig.is_loop and sig.justified:
            suppressed.append(f"{case_id}: reassignment loop justified by SHIFT_CHANGE handover (structural.py)")

    for case_id, violation in card_violations.items():
        sig = signals_by_case.get(case_id)
        if sig is not None:
            reason = "already flagged as REASSIGNMENT_LOOP" if sig.flagged else (
                "justified by SHIFT_CHANGE handover" if sig.is_loop else
                "not a genuine loop (distinct analysts, no repeated target) — count-only false-positive shape"
            )
            suppressed.append(f"{case_id}: REASSIGN-CARD-001 suppressed, {reason}")
            continue
        concerns.append(
            _make_package(
                finding_id=next_finding_id(),
                finding_type="EXCESSIVE_REASSIGNMENT_CARDINALITY",
                capability=violation.capability,
                authority=violation.authority,
                rule_id=violation.rule_id,
                rule_version="1.0",
                primary_id=case_id,
                event_ids=_event_ids_for_case(ocel, case_id, "REASSIGN"),
                assumptions_notes=[violation.detail],
                cse_id=cse_id, low_confidence_cases=low_confidence,
            )
        )

    for case_id, violation in esc_violations.items():
        concerns.append(
            _make_package(
                finding_id=next_finding_id(),
                finding_type="ESCALATION_SLA_VIOLATION",
                capability=violation.capability,
                authority=violation.authority,
                rule_id=violation.rule_id,
                rule_version="1.0",
                primary_id=case_id,
                event_ids=_event_ids_for_case(ocel, case_id, "ESCALATE"),
                assumptions_notes=[violation.detail],
                cse_id=cse_id, low_confidence_cases=low_confidence,
            )
        )

    for case_id, violation in enr_violations.items():
        concerns.append(
            _make_package(
                finding_id=next_finding_id(),
                finding_type="MISSING_ENRICHMENT",
                capability=violation.capability,
                authority=violation.authority,
                rule_id=violation.rule_id,
                rule_version="1.0",
                primary_id=case_id,
                event_ids=_event_ids_for_case(ocel, case_id, "INVESTIGATE"),
                assumptions_notes=[violation.detail],
                cse_id=cse_id, low_confidence_cases=low_confidence,
            )
        )

    # --- Phase C detectors: fast-close, asset recurrence, low telemetry, ---
    # --- investigation uniformity — same fuse-into-Concern pattern as above. ---

    severity_map = _case_severity_map(ocel)
    fast_signals = {s.case_id: s for s in detect_fast_close(ocel)}
    cases_by_severity: dict[str, list[str]] = {}
    for case_id, sev in severity_map.items():
        if case_id in fast_signals:
            cases_by_severity.setdefault(sev, []).append(case_id)
    severity_observations = [
        PeerGroupObservation(group_id=sev, exposure=len(cases), observed=sum(1 for c in cases if not fast_signals[c].is_fast))
        for sev, cases in cases_by_severity.items()
    ]
    for finding in detect_negative_space(severity_observations):
        if not finding.flagged:
            continue
        for case_id in cases_by_severity[finding.group_id]:
            if fast_signals[case_id].is_fast:
                concerns.append(
                    _make_package(
                        finding_id=next_finding_id(),
                        finding_type="FAST_CLOSE_OUTLIER",
                        capability="Investigation",
                        authority="PEER_NORMAL",
                        rule_id=None, rule_version=None,
                        primary_id=case_id,
                        event_ids=_event_ids_for_case(ocel, case_id, "CLOSE"),
                        assumptions_notes=[
                            f"This case closed in just {fast_signals[case_id].duration_minutes:.0f} minutes — much "
                            f"faster than other {finding.group_id.lower()}-severity cases typically take here. "
                            "Unusual, not automatically wrong — worth a quick look at whether it was genuinely "
                            "resolved or just closed out.",
                            f"severity={finding.group_id}, duration_minutes={fast_signals[case_id].duration_minutes:.1f}, "
                            f"peer group z_score={finding.z_score:.2f}",
                        ],
                        cse_id=cse_id, low_confidence_cases=low_confidence,
                    )
                )

    for sig in detect_asset_alert_recurrence(ocel):
        if not sig.flagged:
            continue
        concerns.append(
            _make_package(
                finding_id=next_finding_id(),
                finding_type="REPEATED_ALERT_NO_REMEDIATION",
                capability="Incident Response",
                authority="PEER_NORMAL",
                rule_id=None, rule_version=None,
                primary_id=sig.asset_id,
                event_ids=[],
                assumptions_notes=[
                    f"This asset has triggered {sig.alert_count} separate alerts, and none of the linked cases "
                    "show any real investigation activity — worth checking whether the underlying cause was "
                    "ever actually fixed, or if the same problem just keeps re-alerting.",
                    f"alert_count={sig.alert_count}, linked_cases={sig.linked_case_ids}; 'remediated' is a PROXY "
                    "(any linked case reached INVESTIGATE/EVIDENCE_COLLECT), not a ground-truth root-cause-fixed "
                    "determination (docs/assumptions.md).",
                ],
                supporting_cases=list(sig.linked_case_ids),
                cse_id=cse_id, low_confidence_cases=low_confidence,
            )
        )

    for tier in HIGH_CRITICALITY_TIERS:
        tier_assets = [(aid, count) for aid, crit, count in asset_alert_counts(ocel) if crit == tier]
        observations = [PeerGroupObservation(group_id=aid, exposure=1, observed=count) for aid, count in tier_assets]
        for finding in detect_negative_space(observations):
            if not finding.flagged:
                continue
            concerns.append(
                _make_package(
                    finding_id=next_finding_id(),
                    finding_type="LOW_TELEMETRY_CRITICAL_ASSET",
                    capability="Threat Detection",
                    authority="PEER_NORMAL",
                    rule_id=None, rule_version=None,
                    primary_id=finding.group_id,
                    event_ids=[],
                    assumptions_notes=[
                        f"This {tier.lower()}-criticality asset generated only {finding.observed} alert(s) — far "
                        f"fewer than similar {tier.lower()}-criticality assets typically show (expected around "
                        f"{finding.expected:.0f}). Could just be quiet, or could be a monitoring blind spot — "
                        "worth confirming telemetry is actually reaching this asset.",
                        f"criticality_tier={tier}, alert_count={finding.observed} vs. same-tier peer-expected "
                        f"{finding.expected:.1f} (z_score={finding.z_score:.2f}); exposure uniform (=1) per asset — "
                        "no per-asset duty/exposure measure exists in the canonical model yet.",
                    ],
                    cse_id=cse_id, low_confidence_cases=low_confidence,
                )
            )

    for sig in detect_investigation_uniformity(ocel):
        if not sig.flagged:
            continue
        concerns.append(
            _make_package(
                finding_id=next_finding_id(),
                finding_type="REPETITIVE_INVESTIGATION_PATTERN",
                capability="Investigation",
                authority="PEER_NORMAL",
                rule_id=None, rule_version=None,
                primary_id=sig.analyst_id,
                event_ids=[],
                assumptions_notes=[
                    f"Across {sig.num_investigations} different cases, this analyst's time from investigation to "
                    "case-close was nearly identical every single time. That pattern often means the review was a "
                    "quick formality rather than looking closely at each case on its own merits — worth spot-checking "
                    "a few of these cases directly.",
                    f"num_investigations={sig.num_investigations}, coefficient_of_variation="
                    f"{sig.coefficient_of_variation:.3f} — a proxy for template-driven review, not a direct "
                    "measurement of review quality.",
                ],
                supporting_cases=[],
                cse_id=cse_id, low_confidence_cases=low_confidence,
            )
        )

    return FusionResult(concerns=concerns, suppressed=suppressed)
