"""Canonical ingestion schema — the tables and fields every adapter normalizes real
CSE exports into, before `normalization/canonical.py` turns them into the exact
object/event vocabulary `generator/generate.py` already produces (see
docs/assumptions.md for why: every downstream detector in moat1/, okf/, sampling/
was built against that vocabulary, so ingestion's job is to produce it, not invent a
second one).

Only `cases` and `case_events` are required — a real CSE export may not have separate
alerts/assets/analysts/queues tables at all. Everything else is optional and its
absence is reported as reduced capability (quality/validator.py), never fabricated.
"""
from __future__ import annotations

REQUIRED_TABLES = ("cases", "case_events")
OPTIONAL_TABLES = ("alerts", "assets", "analysts", "queues")
ALL_TABLES = REQUIRED_TABLES + OPTIONAL_TABLES

# canonical_field -> required (True) / optional (False), per table.
TABLE_FIELDS: dict[str, dict[str, bool]] = {
    "cases": {
        "case_id": True,
        "analyst_id": False,
        "queue_id": False,
        "status": False,
        "opened_at": False,
        "closed_at": False,
        "alert_id": False,
    },
    "case_events": {
        "case_id": True,
        "event": True,
        "ts": True,
        "actor": False,
        "handover_reason": False,
    },
    "alerts": {
        "alert_id": True,
        "severity": False,
        "category": False,
        "asset_id": False,
        "raised_at": False,
    },
    "assets": {
        "asset_id": True,
        "criticality": False,
        "asset_type": False,
    },
    "analysts": {
        "analyst_id": True,
        "tier": False,
    },
    "queues": {
        "queue_id": True,
        "name": False,
    },
}

# Auto-suggest only — always overridable by the caller (UI or test), never silently
# trusted (Input Validation rule: reject/ask, don't guess-and-proceed on data that
# feeds downstream analytics without confirmation).
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "case_id": ("case_id", "incident_number", "ticket_id"),
    "analyst_id": ("analyst_id", "assigned_to", "owner", "analyst"),
    "queue_id": ("queue_id", "assignment_group", "queue", "team"),
    "status": ("status", "state"),
    "opened_at": ("opened_at", "created", "created_at", "open_time"),
    "closed_at": ("closed_at", "resolved_at", "close_time"),
    "alert_id": ("alert_id", "alert", "source_alert_id"),
    "event": ("event", "event_type", "activity", "action"),
    "ts": ("ts", "timestamp", "time", "event_time"),
    "actor": ("actor", "analyst_id", "assigned_to", "owner"),
    "handover_reason": ("handover_reason", "reason", "notes"),
    "severity": ("severity", "priority"),
    "category": ("category", "type"),
    "asset_id": ("asset_id", "ci_id", "asset"),
    "raised_at": ("raised_at", "created", "created_at"),
    "criticality": ("criticality", "impact", "importance"),
    "asset_type": ("asset_type", "ci_type", "type"),
    "tier": ("tier", "level"),
    "name": ("name", "queue_name"),
}

# Free-text case_events.event values -> canonical OCEL event type. Anything not
# matched here is skipped (reported, not silently dropped) rather than guessed.
EVENT_TYPE_ALIASES: dict[str, str] = {
    "assign": "ASSIGN", "assigned": "ASSIGN",
    "reassign": "REASSIGN", "reassigned": "REASSIGN", "transfer": "REASSIGN", "transferred": "REASSIGN",
    "enrich": "ENRICH", "enrichment": "ENRICH", "enriched": "ENRICH",
    "investigate": "INVESTIGATE", "investigation": "INVESTIGATE", "investigated": "INVESTIGATE",
    "escalate": "ESCALATE", "escalated": "ESCALATE", "escalation": "ESCALATE",
    "evidence_collect": "EVIDENCE_COLLECT", "evidence_collected": "EVIDENCE_COLLECT", "evidence": "EVIDENCE_COLLECT",
    "close": "CLOSE", "closed": "CLOSE", "resolved": "CLOSE", "resolve": "CLOSE",
}


def suggest_mapping(table: str, source_columns: list[str]) -> dict[str, str | None]:
    """Best-effort canonical_field -> source_column guess for one table's detected
    columns. Returns None for any canonical field with no confident match — the
    caller (UI or test) must fill or confirm those before ingestion runs."""
    lowered = {c.lower(): c for c in source_columns}
    guess: dict[str, str | None] = {}
    for field in TABLE_FIELDS.get(table, {}):
        match = None
        for alias in FIELD_ALIASES.get(field, (field,)):
            if alias in lowered:
                match = lowered[alias]
                break
        guess[field] = match
    return guess
