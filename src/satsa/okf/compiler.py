"""OKF declarative constraint compiler (build spec Section 6.5).

Verified per Section 7.3 before relying on it: DuckDB's `sqlite` extension can attach
an OCEL 2.0 SQLite file directly and query its tables (confirmed locally — attach,
count events, read a type-specific table's rows — before this module was written).

Each of the four templates (Response, Precedence, Cardinality, Not-Co-Existence) is
evaluated as SQL joins over the OCEL-derived tables (case_events, case_context below),
with the actual time-window arithmetic done in Python after the relevant rows are
fetched — DuckDB handles the relational join/filter work; Python handles the
timedelta comparison, which is simpler and easier to get right than embedding dynamic
interval arithmetic in generated SQL strings.
"""
from __future__ import annotations

from datetime import datetime

import duckdb

from satsa.okf.schema import OKFRule, Violation


def connect(sqlite_path: str) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("INSTALL sqlite")
    conn.execute("LOAD sqlite")
    conn.execute(f"ATTACH '{sqlite_path}' AS ocel (TYPE sqlite)")
    _build_views(conn)
    return conn


def _build_views(conn: duckdb.DuckDBPyConnection) -> None:
    event_types = [r[0] for r in conn.execute("SELECT ocel_type_map FROM ocel.event_map_type").fetchall()]
    union_sql = " UNION ALL ".join(f'SELECT ocel_id, ocel_time FROM ocel.event_{t}' for t in event_types)
    conn.execute(f"CREATE OR REPLACE VIEW event_times AS {union_sql}")

    conn.execute(
        """
        CREATE OR REPLACE VIEW case_events AS
        SELECT eo.ocel_object_id AS case_id, e.ocel_id AS event_id, e.ocel_type AS event_type, et.ocel_time AS event_time
        FROM ocel.event_object eo
        JOIN ocel.event e ON e.ocel_id = eo.ocel_event_id
        JOIN event_times et ON et.ocel_id = e.ocel_id
        JOIN ocel.object o ON o.ocel_id = eo.ocel_object_id AND o.ocel_type = 'Case'
        WHERE eo.ocel_qualifier LIKE '%\\_for\\_case' ESCAPE '\\'
        """
    )

    # case_context is domain-specific to the SOC schema (Section 6.5's authority
    # conditions like "severity=CRITICAL, asset_criticality=HIGH" only make sense once
    # Alert/Asset object types exist) — build it only when both are present, so this
    # compiler still works over an OCEL log that doesn't model a SOC at all (e.g. a
    # synthetic fixture exercising just one constraint template in isolation).
    object_types = {r[0] for r in conn.execute("SELECT ocel_type FROM ocel.object_map_type").fetchall()}
    if {"Alert", "Asset"} <= object_types:
        conn.execute(
            """
            CREATE OR REPLACE VIEW case_context AS
            SELECT
                co.ocel_source_id AS case_id,
                al_attr.severity AS alert_severity,
                ast_attr.criticality AS asset_criticality
            FROM ocel.object_object co
            JOIN ocel.object_object ao
                ON ao.ocel_source_id = co.ocel_target_id AND ao.ocel_qualifier = 'raised_on_asset'
            JOIN ocel.object_Alert al_attr
                ON al_attr.ocel_id = co.ocel_target_id AND al_attr.ocel_time = '1970-01-01T00:00:00Z'
            JOIN ocel.object_Asset ast_attr
                ON ast_attr.ocel_id = ao.ocel_target_id AND ast_attr.ocel_time = '1970-01-01T00:00:00Z'
            WHERE co.ocel_qualifier = 'case_for_alert'
            """
        )


def _case_filter_sql(conditions: dict) -> str:
    clauses = []
    for col, val in conditions.items():
        if isinstance(val, (list, tuple, set)):
            values = ", ".join(f"'{v}'" for v in val)
            clauses.append(f"{col} IN ({values})")
        else:
            clauses.append(f"{col} = '{val}'")
    return " AND ".join(clauses) if clauses else "TRUE"


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def evaluate_response(conn: duckdb.DuckDBPyConnection, rule: OKFRule) -> list[Violation]:
    filter_sql = _case_filter_sql(rule.applies_when)
    triggered_cases = [r[0] for r in conn.execute(f"SELECT case_id FROM case_context WHERE {filter_sql}").fetchall()]
    expected_type = rule.expected_behavior["event_type"]

    violations = []
    for case_id in triggered_cases:
        rows = conn.execute(
            "SELECT event_type, event_time FROM case_events WHERE case_id = ? ORDER BY event_time", [case_id]
        ).fetchall()
        if not rows:
            continue
        case_start = _parse_time(rows[0][1])
        expected_rows = [r for r in rows if r[0] == expected_type]
        if not expected_rows:
            violations.append(
                Violation(rule.rule_id, case_id, rule.capability, rule.authority, f"{expected_type} never occurred")
            )
            continue
        if rule.time_constraint is not None:
            expected_time = _parse_time(expected_rows[0][1])
            elapsed = expected_time - case_start
            if not _compare(elapsed, rule.time_constraint):
                violations.append(
                    Violation(
                        rule.rule_id,
                        case_id,
                        rule.capability,
                        rule.authority,
                        f"{expected_type} occurred after {elapsed}, violating {rule.time_constraint}",
                    )
                )
    return violations


def _compare(elapsed, tc) -> bool:
    bound = tc.to_timedelta()
    ops = {
        "<=": elapsed <= bound,
        "<": elapsed < bound,
        ">=": elapsed >= bound,
        ">": elapsed > bound,
        "==": elapsed == bound,
    }
    return ops[tc.operator]


def evaluate_precedence(conn: duckdb.DuckDBPyConnection, rule: OKFRule) -> list[Violation]:
    before_type = rule.applies_when["must_occur_before_type"]
    after_type = rule.expected_behavior["event_type"]

    rows = conn.execute(
        "SELECT case_id, event_type, event_time FROM case_events WHERE event_type IN (?, ?) ORDER BY case_id, event_time",
        [before_type, after_type],
    ).fetchall()

    by_case: dict[str, list[tuple[str, str]]] = {}
    for case_id, event_type, event_time in rows:
        by_case.setdefault(case_id, []).append((event_type, event_time))

    violations = []
    for case_id, events in by_case.items():
        seen_before = False
        for event_type, _ in events:
            if event_type == before_type:
                seen_before = True
            elif event_type == after_type and not seen_before:
                violations.append(
                    Violation(
                        rule.rule_id,
                        case_id,
                        rule.capability,
                        rule.authority,
                        f"{after_type} occurred without a prior {before_type}",
                    )
                )
    return violations


def evaluate_cardinality(conn: duckdb.DuckDBPyConnection, rule: OKFRule) -> list[Violation]:
    event_type = rule.applies_when["event_type"]
    operator = rule.expected_behavior["operator"]
    bound = rule.expected_behavior["value"]

    rows = conn.execute(
        "SELECT case_id, COUNT(*) FROM case_events WHERE event_type = ? GROUP BY case_id", [event_type]
    ).fetchall()

    ops = {
        "<=": lambda n: n <= bound,
        "<": lambda n: n < bound,
        ">=": lambda n: n >= bound,
        ">": lambda n: n > bound,
        "==": lambda n: n == bound,
    }
    check = ops[operator]

    return [
        Violation(rule.rule_id, case_id, rule.capability, rule.authority, f"{event_type} occurred {count} times")
        for case_id, count in rows
        if not check(count)
    ]


def evaluate_not_co_existence(conn: duckdb.DuckDBPyConnection, rule: OKFRule) -> list[Violation]:
    type_a = rule.applies_when["event_type_a"]
    type_b = rule.expected_behavior["event_type_b"]

    rows = conn.execute(
        """
        SELECT a.case_id FROM
            (SELECT DISTINCT case_id FROM case_events WHERE event_type = ?) a
        JOIN
            (SELECT DISTINCT case_id FROM case_events WHERE event_type = ?) b
        ON a.case_id = b.case_id
        """,
        [type_a, type_b],
    ).fetchall()

    return [
        Violation(rule.rule_id, case_id, rule.capability, rule.authority, f"{type_a} and {type_b} both occurred")
        for (case_id,) in rows
    ]


_EVALUATORS = {
    "RESPONSE": evaluate_response,
    "PRECEDENCE": evaluate_precedence,
    "CARDINALITY": evaluate_cardinality,
    "NOT_CO_EXISTENCE": evaluate_not_co_existence,
}


def evaluate_rule(conn: duckdb.DuckDBPyConnection, rule: OKFRule) -> list[Violation]:
    return _EVALUATORS[rule.constraint_template](conn, rule)
