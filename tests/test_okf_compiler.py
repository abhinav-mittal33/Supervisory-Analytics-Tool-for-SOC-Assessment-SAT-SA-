"""Build Order Step 6 — OKF declarative constraint compiler.

Not one of the six numbered Gates, but still held to the same standard: each
template's compiled-SQL result is checked against an independent, hand-written Python
oracle over the same OCEL objects/events (not sharing any code path with the
compiler), so a bug in the DuckDB SQL wouldn't silently pass just because the compiler
agrees with itself.
"""
from datetime import timedelta

from satsa.generator.generate import generate
from satsa.generator.profiles import MATURE_CSE_DEV
from satsa.ocel import sqlite_io
from satsa.okf import compiler, rules


def _oracle_esc_crit_violations(ocel) -> set[str]:
    alerts = {o.id: {a.name: a.value for a in o.attributes} for o in ocel.objects if o.type == "Alert"}
    assets = {o.id: {a.name: a.value for a in o.attributes} for o in ocel.objects if o.type == "Asset"}
    case_to_alert, alert_to_asset = {}, {}
    for o in ocel.objects:
        if o.type == "Case":
            for r in o.relationships:
                if r.qualifier == "case_for_alert":
                    case_to_alert[o.id] = r.target_id
        if o.type == "Alert":
            for r in o.relationships:
                if r.qualifier == "raised_on_asset":
                    alert_to_asset[o.id] = r.target_id

    assign_time, escalate_time = {}, {}
    for e in ocel.events:
        for r in e.relationships:
            if e.type == "ASSIGN" and r.qualifier == "assignment_for_case":
                assign_time[r.target_id] = e.time
            if e.type == "ESCALATE" and r.qualifier == "escalation_for_case":
                escalate_time[r.target_id] = e.time

    violations = set()
    for case_id, alert_id in case_to_alert.items():
        severity = alerts.get(alert_id, {}).get("severity")
        crit = assets.get(alert_to_asset.get(alert_id), {}).get("criticality")
        if severity == "CRITICAL" and crit in ("HIGH", "CRITICAL"):
            if case_id not in escalate_time:
                violations.add(case_id)
            elif escalate_time[case_id] - assign_time[case_id] > timedelta(minutes=30):
                violations.add(case_id)
    return violations


def _oracle_enr_prec_violations(ocel) -> set[str]:
    enrich_time, investigate_time = {}, {}
    for e in ocel.events:
        for r in e.relationships:
            if e.type == "ENRICH" and r.qualifier == "enrich_for_case":
                enrich_time[r.target_id] = e.time
            if e.type == "INVESTIGATE" and r.qualifier == "investigate_for_case":
                investigate_time[r.target_id] = e.time
    return {
        case_id
        for case_id, inv_t in investigate_time.items()
        if case_id not in enrich_time or enrich_time[case_id] > inv_t
    }


def _oracle_reassign_card_violations(ocel) -> set[str]:
    counts: dict[str, int] = {}
    for e in ocel.events:
        if e.type != "REASSIGN":
            continue
        for r in e.relationships:
            if r.qualifier == "reassignment_for_case":
                counts[r.target_id] = counts.get(r.target_id, 0) + 1
    return {case_id for case_id, n in counts.items() if n > 2}


def test_response_precedence_cardinality_templates_match_independent_oracle(tmp_path):
    ocel, _ = generate(MATURE_CSE_DEV)
    sqlite_path = str(tmp_path / "okf_test.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)

    esc_violations = {v.case_id for v in compiler.evaluate_rule(conn, rules.ESC_CRIT_001)}
    assert esc_violations == _oracle_esc_crit_violations(ocel)
    assert esc_violations, "no CRITICAL/HIGH-asset escalation-duty cases generated — test is vacuous"

    enr_violations = {v.case_id for v in compiler.evaluate_rule(conn, rules.ENR_PREC_001)}
    assert enr_violations == _oracle_enr_prec_violations(ocel)
    assert enr_violations, "no missing-enrichment cases generated — test is vacuous"

    card_violations = {v.case_id for v in compiler.evaluate_rule(conn, rules.REASSIGN_CARD_001)}
    assert card_violations == _oracle_reassign_card_violations(ocel)
    assert card_violations, "no >2-reassignment cases generated — test is vacuous"

    # Section 9.1's point, made concrete: this simple Cardinality rule also flags the
    # REASSIGNMENT_CHAIN_NO_LOOP hard case (3 reassignments, 3 distinct analysts, no
    # repeat) exactly like a real loop — it cannot tell them apart, which is exactly
    # why detect_reassignment_loops exists as a separate, genuinely object-centric
    # detector instead of this rule being treated as sufficient on its own.
    from satsa.moat1.structural import detect_reassignment_loops

    signals = detect_reassignment_loops(ocel)
    real_loop_cases = {s.case_id for s in signals if s.is_loop}
    chain_cases_flagged_by_cardinality_rule = card_violations - real_loop_cases
    assert chain_cases_flagged_by_cardinality_rule, (
        "expected the naive cardinality rule to also (mis)flag non-loop reassignment chains"
    )


def test_not_co_existence_template_on_a_synthetic_fixture(tmp_path):
    """No naturally-occurring mutually-exclusive event pair exists in this generator's
    lifecycle yet, so this template is verified against a small hand-built fixture
    rather than real generated data — documented here rather than dressed up as a
    realistic OKF rule the generator actually exercises."""
    from datetime import datetime, timezone

    from satsa.ocel.model import EPOCH, OCEL, AttributeDef, Event, Obj, Relationship, TypeDef

    ocel = OCEL()
    ocel.object_types = [TypeDef("Case", ())]
    ocel.event_types = [TypeDef("EVENT_A", ()), TypeDef("EVENT_B", ())]
    ocel.objects = [Obj("C1", "Case", (), ()), Obj("C2", "Case", (), ())]
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ocel.events = [
        Event("e1", "EVENT_A", t, (), (Relationship("C1", "a_for_case"),)),
        Event("e2", "EVENT_B", t, (), (Relationship("C1", "b_for_case"),)),
        Event("e3", "EVENT_A", t, (), (Relationship("C2", "a_for_case"),)),
    ]
    sqlite_path = str(tmp_path / "notco_test.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)

    rule = rules.OKFRule(
        rule_id="TEST-NOTCO-001",
        capability="Operational Discipline",
        authority="OPTIONAL",
        constraint_template="NOT_CO_EXISTENCE",
        source_type="APPROVED_SOP",
        source_reference="synthetic_fixture",
        applies_when={"event_type_a": "EVENT_A"},
        expected_behavior={"event_type_b": "EVENT_B"},
    )
    violations = {v.case_id for v in compiler.evaluate_rule(conn, rule)}
    assert violations == {"C1"}
