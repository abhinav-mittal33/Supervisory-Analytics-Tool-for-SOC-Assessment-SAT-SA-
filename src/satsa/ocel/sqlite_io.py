"""OCEL 2.0 relational (SQLite) format — read/write.

Table structure implements Section 6 of the OCEL 2.0 Specification (Berti et al.,
arXiv:2403.01975, CC BY 4.0 — see docs/references.md) directly: this build does not
depend on pm4py/ocpa (docs/assumptions.md entry 001), so every table, primary key,
and foreign key below is hand-implemented against the spec text, not copied from a
reference implementation.

Tables: event_map_type, object_map_type, event, object, one event_<T> table per event
type, one object_<T> table per object type (with the ocel_changed_field
attribute-history pattern), event_object (E2O), object_object (O2O).
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from satsa.ocel.model import (
    EPOCH,
    OCEL,
    AttributeDef,
    EventAttributeValue,
    ObjectAttributeValue,
    Relationship,
    TypeDef,
    Event,
    Obj,
)


def _ident(name: str) -> str:
    """Injective-enough mapping from a type name to a safe SQL table-name suffix."""
    return re.sub(r"[^0-9a-zA-Z_]", "", name.replace(" ", ""))


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _fmt_time(t: datetime) -> str:
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    # isoformat() keeps microseconds when present — strftime's %S silently truncates
    # sub-second precision, which broke round-trip identity (Gate 0).
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def write_sqlite(ocel: OCEL, path: str) -> None:
    Path(path).unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.execute("CREATE TABLE event_map_type (ocel_type TEXT PRIMARY KEY, ocel_type_map TEXT NOT NULL)")
    cur.execute("CREATE TABLE object_map_type (ocel_type TEXT PRIMARY KEY, ocel_type_map TEXT NOT NULL)")
    for et in ocel.event_types:
        cur.execute("INSERT INTO event_map_type VALUES (?, ?)", (et.name, _ident(et.name)))
    for ot in ocel.object_types:
        cur.execute("INSERT INTO object_map_type VALUES (?, ?)", (ot.name, _ident(ot.name)))

    cur.execute(
        "CREATE TABLE event (ocel_id TEXT PRIMARY KEY, ocel_type TEXT NOT NULL, "
        "FOREIGN KEY (ocel_type) REFERENCES event_map_type(ocel_type))"
    )
    cur.execute(
        "CREATE TABLE object (ocel_id TEXT PRIMARY KEY, ocel_type TEXT NOT NULL, "
        "FOREIGN KEY (ocel_type) REFERENCES object_map_type(ocel_type))"
    )

    type_by_name: dict[str, TypeDef] = {t.name: t for t in (*ocel.event_types, *ocel.object_types)}

    for et in ocel.event_types:
        table = "event_" + _ident(et.name)
        cols = ", ".join(f"{_q(a.name)} TEXT" for a in et.attributes)
        cur.execute(
            f"CREATE TABLE {_q(table)} (ocel_id TEXT PRIMARY KEY, ocel_time TEXT NOT NULL"
            + (", " + cols if cols else "")
            + ", FOREIGN KEY (ocel_id) REFERENCES event(ocel_id))"
        )

    for ot in ocel.object_types:
        table = "object_" + _ident(ot.name)
        cols = ", ".join(f"{_q(a.name)} TEXT" for a in ot.attributes)
        cur.execute(
            f"CREATE TABLE {_q(table)} (ocel_id TEXT NOT NULL, ocel_time TEXT NOT NULL"
            + (", " + cols if cols else "")
            + ", ocel_changed_field TEXT, PRIMARY KEY (ocel_id, ocel_time), "
            "FOREIGN KEY (ocel_id) REFERENCES object(ocel_id))"
        )

    cur.execute(
        "CREATE TABLE event_object (ocel_event_id TEXT NOT NULL, ocel_object_id TEXT NOT NULL, "
        "ocel_qualifier TEXT NOT NULL, PRIMARY KEY (ocel_event_id, ocel_object_id, ocel_qualifier), "
        "FOREIGN KEY (ocel_event_id) REFERENCES event(ocel_id), "
        "FOREIGN KEY (ocel_object_id) REFERENCES object(ocel_id))"
    )
    cur.execute(
        "CREATE TABLE object_object (ocel_source_id TEXT NOT NULL, ocel_target_id TEXT NOT NULL, "
        "ocel_qualifier TEXT NOT NULL, PRIMARY KEY (ocel_source_id, ocel_target_id, ocel_qualifier), "
        "FOREIGN KEY (ocel_source_id) REFERENCES object(ocel_id), "
        "FOREIGN KEY (ocel_target_id) REFERENCES object(ocel_id))"
    )

    # Pass 1: all event/object rows (generic + type-specific), no relationship rows yet —
    # relationships can point forward/backward across the events/objects lists, so every
    # row with a primary key must exist before any foreign key referencing it is inserted.
    for e in ocel.events:
        cur.execute("INSERT INTO event VALUES (?, ?)", (e.id, e.type))
        table = "event_" + _ident(e.type)
        attr_defs = type_by_name[e.type].attributes
        names = [a.name for a in attr_defs]
        values = {a.name: str(a.value) for a in e.attributes}
        placeholders = ", ".join(["?", "?"] + ["?"] * len(names))
        cur.execute(
            f"INSERT INTO {_q(table)} (ocel_id, ocel_time" + "".join(f", {_q(n)}" for n in names) + ")"
            f" VALUES ({placeholders})",
            [e.id, _fmt_time(e.time)] + [values.get(n) for n in names],
        )

    for o in ocel.objects:
        cur.execute("INSERT INTO object VALUES (?, ?)", (o.id, o.type))
        table = "object_" + _ident(o.type)
        attr_defs = type_by_name[o.type].attributes
        names = [a.name for a in attr_defs]

        initial = {a.name: a.value for a in o.attributes if a.time == EPOCH}
        if initial or not o.attributes:
            row = [initial.get(n) for n in names]
            cur.execute(
                f"INSERT INTO {_q(table)} (ocel_id, ocel_time"
                + "".join(f", {_q(n)}" for n in names)
                + ", ocel_changed_field) VALUES (?, ?"
                + ", ?" * len(names)
                + ", NULL)",
                [o.id, _fmt_time(EPOCH)] + [str(v) if v is not None else None for v in row],
            )
        for a in o.attributes:
            if a.time == EPOCH:
                continue
            row = [a.value if n == a.name else None for n in names]
            cur.execute(
                f"INSERT INTO {_q(table)} (ocel_id, ocel_time"
                + "".join(f", {_q(n)}" for n in names)
                + ", ocel_changed_field) VALUES (?, ?"
                + ", ?" * len(names)
                + ", ?)",
                [o.id, _fmt_time(a.time)] + [str(v) if v is not None else None for v in row] + [a.name],
            )

    # Pass 2: relationship rows, now that every event/object row exists.
    for e in ocel.events:
        for r in e.relationships:
            cur.execute("INSERT INTO event_object VALUES (?, ?, ?)", (e.id, r.target_id, r.qualifier))
    for o in ocel.objects:
        for r in o.relationships:
            cur.execute("INSERT INTO object_object VALUES (?, ?, ?)", (o.id, r.target_id, r.qualifier))

    conn.commit()
    conn.close()


def read_sqlite(path: str) -> OCEL:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    ocel = OCEL()

    event_type_names = {
        r["ocel_type"]: r["ocel_type_map"] for r in cur.execute("SELECT * FROM event_map_type").fetchall()
    }
    object_type_names = {
        r["ocel_type"]: r["ocel_type_map"] for r in cur.execute("SELECT * FROM object_map_type").fetchall()
    }

    for type_name, mapped in event_type_names.items():
        table = "event_" + mapped
        cols = [
            c[1]
            for c in conn.execute(f"PRAGMA table_info({_q(table)})").fetchall()
            if c[1] not in ("ocel_id", "ocel_time")
        ]
        ocel.event_types.append(TypeDef(type_name, tuple(AttributeDef(c, "string") for c in cols)))

    for type_name, mapped in object_type_names.items():
        table = "object_" + mapped
        cols = [
            c[1]
            for c in conn.execute(f"PRAGMA table_info({_q(table)})").fetchall()
            if c[1] not in ("ocel_id", "ocel_time", "ocel_changed_field")
        ]
        ocel.object_types.append(TypeDef(type_name, tuple(AttributeDef(c, "string") for c in cols)))

    # Materialize each outer result set before running nested queries — a sqlite3
    # Cursor is invalidated by re-executing it, so reusing one cursor for a nested
    # query mid-iteration silently truncates the outer loop instead of erroring.
    for e_row in cur.execute("SELECT * FROM event").fetchall():
        eid, etype = e_row["ocel_id"], e_row["ocel_type"]
        table = "event_" + event_type_names[etype]
        detail = conn.execute(f"SELECT * FROM {_q(table)} WHERE ocel_id = ?", (eid,)).fetchone()
        attr_names = [k for k in detail.keys() if k not in ("ocel_id", "ocel_time")]
        attrs = tuple(
            EventAttributeValue(n, detail[n]) for n in attr_names if detail[n] is not None
        )
        rels = tuple(
            Relationship(r["ocel_object_id"], r["ocel_qualifier"])
            for r in conn.execute(
                "SELECT ocel_object_id, ocel_qualifier FROM event_object WHERE ocel_event_id = ?", (eid,)
            ).fetchall()
        )
        ocel.events.append(Event(eid, etype, _parse_time(detail["ocel_time"]), attrs, rels))

    for o_row in cur.execute("SELECT * FROM object").fetchall():
        oid, otype = o_row["ocel_id"], o_row["ocel_type"]
        table = "object_" + object_type_names[otype]
        attrs: list[ObjectAttributeValue] = []
        for detail in conn.execute(
            f"SELECT * FROM {_q(table)} WHERE ocel_id = ? ORDER BY ocel_time", (oid,)
        ).fetchall():
            t = _parse_time(detail["ocel_time"])
            changed = detail["ocel_changed_field"]
            attr_names = [k for k in detail.keys() if k not in ("ocel_id", "ocel_time", "ocel_changed_field")]
            if changed is None:
                for n in attr_names:
                    if detail[n] is not None:
                        attrs.append(ObjectAttributeValue(n, detail[n], t))
            else:
                attrs.append(ObjectAttributeValue(changed, detail[changed], t))
        rels = tuple(
            Relationship(r["ocel_target_id"], r["ocel_qualifier"])
            for r in conn.execute(
                "SELECT ocel_target_id, ocel_qualifier FROM object_object WHERE ocel_source_id = ?", (oid,)
            ).fetchall()
        )
        ocel.objects.append(Obj(oid, otype, tuple(attrs), rels))

    conn.close()
    return ocel
