"""Canonical-record -> OCEL 2.0 builder. Produces the exact object/event vocabulary
`generator/generate.py` produces (same type names, same relationship qualifiers) so
every existing detector (moat1/, okf/, sampling/) consumes ingested data unmodified —
see the plan's "Canonical target" section for the full mapping table this file
implements.

Every object gets a `cse_id` attribute (new — the synthetic generator doesn't need
one, since it only ever produces a single CSE's data at a time) so multiple CSEs'
ingested data can coexist in one OCEL instance without mixing entities.

Missing optional inputs (no assets/analysts/queues table) get an explicit
"UNKNOWN"-tagged stand-in object, not a fabricated real value — the same idiom this
codebase already uses for authority classes it can't defensibly assign
(`ui/app.py::AUTHORITY_LABELS["UNKNOWN"]`).
"""
from __future__ import annotations

from datetime import datetime, timezone

from satsa.ocel.model import (
    EPOCH,
    OCEL,
    AttributeDef,
    Event,
    EventAttributeValue,
    Obj,
    ObjectAttributeValue,
    Relationship,
    TypeDef,
)
from satsa.ingestion.schema import EVENT_TYPE_ALIASES

_CSE_ID_ATTR = AttributeDef("cse_id", "string")

_OBJECT_TYPES = [
    TypeDef("Asset", (AttributeDef("criticality", "string"), AttributeDef("asset_type", "string"), _CSE_ID_ATTR)),
    TypeDef("Alert", (AttributeDef("severity", "string"), AttributeDef("category", "string"), _CSE_ID_ATTR)),
    TypeDef("Case", (AttributeDef("status", "string"), _CSE_ID_ATTR)),
    TypeDef("Analyst", (AttributeDef("tier", "string"), _CSE_ID_ATTR)),
    TypeDef("Queue", (AttributeDef("name", "string"), _CSE_ID_ATTR)),
]

_EVENT_TYPES = [
    TypeDef("ALERT_RAISED", ()),
    TypeDef("OPEN_CASE", ()),
    TypeDef("ASSIGN", ()),
    TypeDef("ENRICH", ()),
    TypeDef("INVESTIGATE", ()),
    TypeDef("ESCALATE", ()),
    TypeDef("EVIDENCE_COLLECT", ()),
    TypeDef("REASSIGN", (AttributeDef("handover_reason", "string"),)),
    TypeDef("CLOSE", ()),
]


def _parse_time(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip().replace("Z", "+00:00")
    try:
        t = datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def build_ocel(tables: dict[str, list[dict]], cse_id: str) -> OCEL:
    ocel = OCEL(event_types=list(_EVENT_TYPES), object_types=list(_OBJECT_TYPES))

    def cse_attr() -> ObjectAttributeValue:
        return ObjectAttributeValue("cse_id", cse_id, EPOCH)

    # Assets — from the assets table if present, else a lazily-created "UNKNOWN"
    # stand-in the first time something references an asset_id we haven't seen.
    known_assets: set[str] = set()
    for row in tables.get("assets", []):
        aid = row["asset_id"]
        ocel.objects.append(
            Obj(
                aid, "Asset",
                (
                    ObjectAttributeValue("criticality", row.get("criticality") or "UNKNOWN", EPOCH),
                    ObjectAttributeValue("asset_type", row.get("asset_type") or "UNKNOWN", EPOCH),
                    cse_attr(),
                ),
                (),
            )
        )
        known_assets.add(aid)

    def ensure_asset(aid: str) -> None:
        if aid and aid not in known_assets:
            ocel.objects.append(
                Obj(
                    aid, "Asset",
                    (
                        ObjectAttributeValue("criticality", "UNKNOWN", EPOCH),
                        ObjectAttributeValue("asset_type", "UNKNOWN", EPOCH),
                        cse_attr(),
                    ),
                    (),
                )
            )
            known_assets.add(aid)

    # Analysts and queues — from their tables if present, else inferred (UNKNOWN
    # tier/name) from every analyst_id/queue_id actually referenced by cases/events,
    # so relationships always resolve to a real object.
    known_analysts: set[str] = set()
    for row in tables.get("analysts", []):
        aid = row["analyst_id"]
        ocel.objects.append(Obj(aid, "Analyst", (ObjectAttributeValue("tier", row.get("tier") or "UNKNOWN", EPOCH), cse_attr()), ()))
        known_analysts.add(aid)

    def ensure_analyst(aid: str) -> None:
        if aid and aid not in known_analysts:
            ocel.objects.append(Obj(aid, "Analyst", (ObjectAttributeValue("tier", "UNKNOWN", EPOCH), cse_attr()), ()))
            known_analysts.add(aid)

    known_queues: set[str] = set()
    for row in tables.get("queues", []):
        qid = row["queue_id"]
        ocel.objects.append(Obj(qid, "Queue", (ObjectAttributeValue("name", row.get("name") or qid, EPOCH), cse_attr()), ()))
        known_queues.add(qid)

    def ensure_queue(qid: str) -> None:
        if qid and qid not in known_queues:
            ocel.objects.append(Obj(qid, "Queue", (ObjectAttributeValue("name", qid, EPOCH), cse_attr()), ()))
            known_queues.add(qid)

    # Alerts + ALERT_RAISED events.
    alert_asset: dict[str, str] = {}
    known_alerts: set[str] = set()
    for row in tables.get("alerts", []):
        alert_id = row["alert_id"]
        asset_id = row.get("asset_id")
        if asset_id:
            ensure_asset(asset_id)
            alert_asset[alert_id] = asset_id
        rels = (Relationship(asset_id, "raised_on_asset"),) if asset_id else ()
        ocel.objects.append(
            Obj(
                alert_id, "Alert",
                (
                    ObjectAttributeValue("severity", row.get("severity") or "UNKNOWN", EPOCH),
                    ObjectAttributeValue("category", row.get("category") or "UNKNOWN", EPOCH),
                    cse_attr(),
                ),
                rels,
            )
        )
        known_alerts.add(alert_id)
        raised_at = _parse_time(row.get("raised_at")) or EPOCH
        event_rels = (Relationship(asset_id, "alert_on_asset"),) if asset_id else ()
        ocel.events.append(Event(f"ALERT_RAISED::{alert_id}", "ALERT_RAISED", raised_at, (), event_rels))

    # Cases + OPEN_CASE/ASSIGN + whatever case_events map to.
    for row in tables.get("cases", []):
        case_id = row["case_id"]
        analyst_id = row.get("analyst_id")
        queue_id = row.get("queue_id")
        alert_id = row.get("alert_id")

        case_attrs = [ObjectAttributeValue("status", row.get("status") or "OPEN", EPOCH), cse_attr()]
        case_rels = []
        if alert_id and alert_id in known_alerts:
            case_rels.append(Relationship(alert_id, "case_for_alert"))
        if analyst_id:
            ensure_analyst(analyst_id)
            case_rels.append(Relationship(analyst_id, "current_assignee"))
        if queue_id:
            ensure_queue(queue_id)
            case_rels.append(Relationship(queue_id, "current_queue"))

        opened_at = _parse_time(row.get("opened_at")) or EPOCH
        open_rels = (Relationship(alert_id, "opened_from_alert"),) if alert_id and alert_id in known_alerts else ()
        ocel.events.append(Event(f"OPEN_CASE::{case_id}", "OPEN_CASE", opened_at, (), open_rels))

        if analyst_id or queue_id:
            assign_rels = [Relationship(case_id, "assignment_for_case")]
            if analyst_id:
                assign_rels.append(Relationship(analyst_id, "assigned_to"))
            if queue_id:
                assign_rels.append(Relationship(queue_id, "routed_via"))
            ocel.events.append(Event(f"ASSIGN::{case_id}", "ASSIGN", opened_at, (), tuple(assign_rels)))

        closed_at = _parse_time(row.get("closed_at"))
        if closed_at:
            case_attrs.append(ObjectAttributeValue("status", "CLOSED", closed_at))

        ocel.objects.append(Obj(case_id, "Case", tuple(case_attrs), tuple(case_rels)))

    # case_events: free-text event -> canonical type, per-event relationships to
    # the case and (where the event type carries an actor qualifier) the analyst.
    ACTOR_QUALIFIER = {"REASSIGN": "reassigned_to", "INVESTIGATE": "investigated_by"}
    counters: dict[str, int] = {}
    for row in tables.get("case_events", []):
        case_id = row["case_id"]
        raw_event = (row.get("event") or "").strip().lower()
        canonical_type = EVENT_TYPE_ALIASES.get(raw_event)
        if canonical_type is None:
            continue  # unrecognized — reported by the quality gate, not guessed here

        ts = _parse_time(row.get("ts")) or EPOCH
        counters[case_id] = counters.get(case_id, 0) + 1
        event_id = f"{canonical_type}::{case_id}::{counters[case_id]}"

        attrs = ()
        if canonical_type == "REASSIGN" and row.get("handover_reason"):
            attrs = (EventAttributeValue("handover_reason", row["handover_reason"]),)

        rels = [Relationship(case_id, _CASE_QUALIFIER[canonical_type])]
        actor = row.get("actor")
        qualifier = ACTOR_QUALIFIER.get(canonical_type)
        if actor and qualifier:
            ensure_analyst(actor)
            rels.append(Relationship(actor, qualifier))

        ocel.events.append(Event(event_id, canonical_type, ts, attrs, tuple(rels)))

    return ocel


_CASE_QUALIFIER = {
    "ASSIGN": "assignment_for_case",
    "REASSIGN": "reassignment_for_case",
    "ENRICH": "enrich_for_case",
    "INVESTIGATE": "investigate_for_case",
    "ESCALATE": "escalation_for_case",
    "EVIDENCE_COLLECT": "evidence_for_case",
    "CLOSE": "close_for_case",
}
