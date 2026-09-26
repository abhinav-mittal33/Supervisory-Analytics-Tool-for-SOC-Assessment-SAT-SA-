"""Data-reliability / ABSTAIN gate (architecture.md's own pipeline diagram names this
stage explicitly). Hard failures (missing required table/field) reject outright —
never silently coerced or dropped, per the Input Validation rule. Missing *optional*
input is reported as reduced capability so the examiner knows which findings this
CSE's data cannot support, rather than the system quietly producing fewer findings
with no explanation."""
from __future__ import annotations

from dataclasses import dataclass, field

from satsa.ingestion.schema import EVENT_TYPE_ALIASES, REQUIRED_TABLES, TABLE_FIELDS


@dataclass
class IngestionReport:
    status: str  # "OK" | "ABSTAIN"
    errors: list[str] = field(default_factory=list)
    reduced_capability: list[str] = field(default_factory=list)
    # case_ids with >=1 case_events row whose 'event' text wasn't recognized — traces
    # a real, per-case evidence-completeness gap so fusion can downgrade evidence_quality
    # precisely, instead of a blanket flag covering every finding regardless of relevance.
    low_confidence_cases: set[str] = field(default_factory=set)


def validate(mapped_tables: dict[str, list[dict]]) -> IngestionReport:
    errors: list[str] = []
    reduced: list[str] = []

    for table in REQUIRED_TABLES:
        rows = mapped_tables.get(table)
        if not rows:
            errors.append(f"required table '{table}' is missing or empty")
            continue
        required_fields = [f for f, req in TABLE_FIELDS[table].items() if req]
        for i, row in enumerate(rows):
            for f in required_fields:
                if not row.get(f):
                    errors.append(f"{table} row {i}: required field '{f}' is missing or empty")

    if errors:
        return IngestionReport(status="ABSTAIN", errors=errors, reduced_capability=reduced)

    case_ids = {r["case_id"] for r in mapped_tables.get("cases", [])}
    for i, row in enumerate(mapped_tables.get("case_events", [])):
        if row["case_id"] not in case_ids:
            errors.append(f"case_events row {i}: case_id {row['case_id']!r} has no matching row in 'cases'")

    unrecognized = {
        row["event"]
        for row in mapped_tables.get("case_events", [])
        if row.get("event") and row["event"].strip().lower() not in EVENT_TYPE_ALIASES
    }
    low_confidence_cases = {
        row["case_id"]
        for row in mapped_tables.get("case_events", [])
        if row.get("event") and row["event"].strip().lower() not in EVENT_TYPE_ALIASES
    }
    if unrecognized:
        reduced.append(
            f"{len(unrecognized)} distinct case_events 'event' value(s) not recognized and will be "
            f"skipped, not guessed: {sorted(unrecognized)}"
        )

    if not mapped_tables.get("alerts"):
        reduced.append("no 'alerts' data — severity/category negative-space and ESCALATION_SLA findings unavailable")
    if not mapped_tables.get("assets"):
        reduced.append("no 'assets' data — asset criticality unavailable, escalation-mandatory detection unavailable")
    if not mapped_tables.get("analysts"):
        reduced.append("no 'analysts' data — analyst tier unavailable, tier-based peer baselines skipped")
    if not mapped_tables.get("queues"):
        reduced.append("no 'queues' data — queue objects inferred from case/case_events references only, no queue name/metadata")

    if errors:
        return IngestionReport(status="ABSTAIN", errors=errors, reduced_capability=reduced)
    return IngestionReport(status="OK", errors=errors, reduced_capability=reduced, low_confidence_cases=low_confidence_cases)
