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
from satsa.moat1.structural import detect_reassignment_loops
from satsa.ocel.model import OCEL
from satsa.okf.compiler import evaluate_rule
from satsa.okf.rules import ENR_PREC_001, ESC_CRIT_001, REASSIGN_CARD_001

EVIDENCE_QUALITY_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}
AUTHORITY_SEVERITY_WEIGHT = {"MANDATORY": 1.0, "EXPECTED": 0.7, "PEER_NORMAL": 0.5, "OPTIONAL": 0.3, "UNKNOWN": 0.1}
CAPABILITY_MATERIALITY = {"Escalation": 1.0, "Investigation": 0.8, "Operational Discipline": 0.5}

# Uniform for this build's synthetic, complete-by-construction data — no simulated
# broken/missing records yet (that's the Data Reliability/ABSTAIN gate, Section 5.3,
# not yet built — see docs/assumptions.md entry 006).
DEFAULT_EVIDENCE_QUALITY = "HIGH"


@dataclass(frozen=True)
class FusionResult:
    concerns: list[EvidencePackage]
    suppressed: list[str]  # human-readable audit notes for signals a finer detector overrode


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
    rule_id: str | None, rule_version: str | None, case_id: str, event_ids: list[str],
    assumptions_notes: list[str],
) -> EvidencePackage:
    evidence_quality = DEFAULT_EVIDENCE_QUALITY
    anomaly_score = 1.0
    conformance_deviation = 1.0
    finding_score = anomaly_score * conformance_deviation * EVIDENCE_QUALITY_WEIGHT[evidence_quality]
    capability_materiality = CAPABILITY_MATERIALITY.get(capability, 0.5)
    severity_weight = AUTHORITY_SEVERITY_WEIGHT[authority]
    concern_score = finding_score * capability_materiality * severity_weight

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
        estimated_review_cost_minutes=15.0,
        affected_objects=[case_id],
        supporting_cases=[case_id],
        supporting_events=event_ids,
        assumptions=assumptions_notes,
        provenance=Provenance(
            source_system="satsa-generator",
            source_file="",
            source_record_id=case_id,
            ingestion_batch_id="",
            ingestion_timestamp="",
            schema_version="1.0",
        ),
    )


def fuse(ocel: OCEL, conn: duckdb.DuckDBPyConnection) -> FusionResult:
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
                    case_id=case_id,
                    event_ids=_event_ids_for_case(ocel, case_id, "REASSIGN"),
                    assumptions_notes=[f"analyst_sequence={sig.analyst_sequence}"],
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
                case_id=case_id,
                event_ids=_event_ids_for_case(ocel, case_id, "REASSIGN"),
                assumptions_notes=[violation.detail],
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
                case_id=case_id,
                event_ids=_event_ids_for_case(ocel, case_id, "ESCALATE"),
                assumptions_notes=[violation.detail],
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
                case_id=case_id,
                event_ids=_event_ids_for_case(ocel, case_id, "INVESTIGATE"),
                assumptions_notes=[violation.detail],
            )
        )

    return FusionResult(concerns=concerns, suppressed=suppressed)
