"""Worked OKF rule examples (Build Order Step 6) — a small registry, not the full
10-20 rule set the pitch deck describes; enough to exercise all four constraint
templates against real generated data.

REASSIGN-CARD-001 is deliberately a weaker check than
src/satsa/moat1/structural.py::detect_reassignment_loops — it exists to make Section
9.1's own point concrete: a generic "count occurrences" OKF Cardinality rule would
flag REASSIGNMENT_CHAIN_NO_LOOP cases (3 reassignments, 3 distinct analysts, no
repeat) exactly as readily as a real ping-pong loop, because it never looks at *which*
analyst is targeted. That's exactly why the structural detector exists as a separate,
genuinely object-centric component rather than being replaced by this rule.
"""
from __future__ import annotations

from satsa.okf.schema import OKFRule, TimeConstraint

ESC_CRIT_001 = OKFRule(
    rule_id="ESC-CRIT-001",
    capability="Escalation",
    authority="MANDATORY",
    constraint_template="RESPONSE",
    source_type="NCIIPC_CRITERIA",
    source_reference="criteria_v3_section_4.2",
    applies_when={"alert_severity": "CRITICAL", "asset_criticality": ["HIGH", "CRITICAL"]},
    expected_behavior={"event_type": "ESCALATE"},
    required_evidence=("escalation_event", "escalation_timestamp"),
    time_constraint=TimeConstraint(operator="<=", value=30, unit="minutes"),
)

ENR_PREC_001 = OKFRule(
    rule_id="ENR-PREC-001",
    capability="Investigation",
    authority="EXPECTED",
    constraint_template="PRECEDENCE",
    source_type="APPROVED_SOP",
    source_reference="investigation_playbook_v1_section_2",
    applies_when={"must_occur_before_type": "ENRICH"},
    expected_behavior={"event_type": "INVESTIGATE"},
    required_evidence=("enrichment_event",),
)

REASSIGN_CARD_001 = OKFRule(
    rule_id="REASSIGN-CARD-001",
    capability="Operational Discipline",
    authority="OPTIONAL",
    constraint_template="CARDINALITY",
    source_type="APPROVED_SOP",
    source_reference="case_handling_playbook_v1_section_5",
    applies_when={"event_type": "REASSIGN"},
    expected_behavior={"operator": "<=", "value": 2},
    required_evidence=(),
)

ALL_RULES = [ESC_CRIT_001, ENR_PREC_001, REASSIGN_CARD_001]
