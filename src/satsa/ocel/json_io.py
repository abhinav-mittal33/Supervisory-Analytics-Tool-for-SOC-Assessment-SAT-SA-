"""OCEL 2.0 JSON format read/write.

Structure matches the official JSON Schema (docs/references.md), confirmed against
the worked example in Section 8.1 of the OCEL 2.0 Specification: attribute values are
always serialized as JSON strings (the `type` field is a semantic hint, not the JSON
value's own type), and timestamps are ISO-8601 with a trailing "Z".
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from satsa.ocel.model import (
    OCEL,
    AttributeDef,
    EventAttributeValue,
    ObjectAttributeValue,
    Relationship,
    TypeDef,
    Event,
    Obj,
)


def _fmt_time(t: datetime) -> str:
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    # isoformat() keeps microseconds when present — strftime's %S silently truncates
    # sub-second precision, which broke round-trip identity (Gate 0).
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(s: str) -> datetime:
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def _fmt_value(v: object) -> str:
    return str(v)


def to_json_dict(ocel: OCEL) -> dict:
    return {
        "eventTypes": [
            {"name": et.name, "attributes": [{"name": a.name, "type": a.type} for a in et.attributes]}
            for et in ocel.event_types
        ],
        "objectTypes": [
            {"name": ot.name, "attributes": [{"name": a.name, "type": a.type} for a in ot.attributes]}
            for ot in ocel.object_types
        ],
        "events": [
            {
                "id": e.id,
                "type": e.type,
                "time": _fmt_time(e.time),
                "attributes": [{"name": a.name, "value": _fmt_value(a.value)} for a in e.attributes],
                "relationships": [
                    {"objectId": r.target_id, "qualifier": r.qualifier} for r in e.relationships
                ],
            }
            for e in ocel.events
        ],
        "objects": [
            {
                "id": o.id,
                "type": o.type,
                "attributes": [
                    {"name": a.name, "value": _fmt_value(a.value), "time": _fmt_time(a.time)}
                    for a in o.attributes
                ],
                "relationships": [
                    {"objectId": r.target_id, "qualifier": r.qualifier} for r in o.relationships
                ],
            }
            for o in ocel.objects
        ],
    }


def from_json_dict(d: dict) -> OCEL:
    ocel = OCEL()
    for et in d.get("eventTypes", []):
        ocel.event_types.append(
            TypeDef(et["name"], tuple(AttributeDef(a["name"], a["type"]) for a in et.get("attributes", [])))
        )
    for ot in d.get("objectTypes", []):
        ocel.object_types.append(
            TypeDef(ot["name"], tuple(AttributeDef(a["name"], a["type"]) for a in ot.get("attributes", [])))
        )
    for e in d.get("events", []):
        ocel.events.append(
            Event(
                id=e["id"],
                type=e["type"],
                time=_parse_time(e["time"]),
                attributes=tuple(
                    EventAttributeValue(a["name"], a["value"]) for a in e.get("attributes", [])
                ),
                relationships=tuple(
                    Relationship(r["objectId"], r["qualifier"]) for r in e.get("relationships", [])
                ),
            )
        )
    for o in d.get("objects", []):
        ocel.objects.append(
            Obj(
                id=o["id"],
                type=o["type"],
                attributes=tuple(
                    ObjectAttributeValue(a["name"], a["value"], _parse_time(a["time"]))
                    for a in o.get("attributes", [])
                ),
                relationships=tuple(
                    Relationship(r["objectId"], r["qualifier"]) for r in o.get("relationships", [])
                ),
            )
        )
    return ocel


def write_json(ocel: OCEL, path: str) -> None:
    with open(path, "w") as f:
        json.dump(to_json_dict(ocel), f, indent=2)


def read_json(path: str) -> OCEL:
    with open(path) as f:
        return from_json_dict(json.load(f))
