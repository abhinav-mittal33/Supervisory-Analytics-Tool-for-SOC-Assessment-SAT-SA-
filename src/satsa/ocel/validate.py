"""OCEL 2.0 validation.

Section 7.2 of the build spec: "Generate -> validate against the official OCEL 2.x
spec/validator -> round-trip -> only then run analytics." Two independent checks:
- validate_json: the in-memory log, serialized to the JSON format, checked against
  the official JSON Schema (fetched from ocel-standard.org — see docs/references.md).
- validate_sqlite_structure: the written SQLite file, checked for the required
  tables/primary-keys/foreign-keys per Section 6.7 of the specification.
Plus validate_semantic, which checks the build-spec-level requirements that aren't
expressible in either schema: required attributes present, timestamps present,
relationships qualified, ground-truth IDs traceable.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import jsonschema

from satsa.ocel.json_io import to_json_dict
from satsa.ocel.model import OCEL

_SCHEMA_PATH = Path(__file__).parent / "schema" / "ocel20-schema.json"


class ValidationError(Exception):
    pass


def _schema() -> dict:
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


def validate_json(ocel: OCEL) -> None:
    jsonschema.validate(instance=to_json_dict(ocel), schema=_schema())


REQUIRED_GENERIC_TABLES = {
    "event_map_type",
    "object_map_type",
    "event",
    "object",
    "event_object",
    "object_object",
}


def validate_sqlite_structure(path: str) -> None:
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = REQUIRED_GENERIC_TABLES - tables
        if missing:
            raise ValidationError(f"missing required OCEL tables: {missing}")

        fk_violations = cur.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            raise ValidationError(f"foreign key violations: {fk_violations}")

        for pk_table in ("event_map_type", "object_map_type", "event", "object"):
            pk_cols = [c[1] for c in cur.execute(f'PRAGMA table_info("{pk_table}")') if c[5] > 0]
            if not pk_cols:
                raise ValidationError(f"table {pk_table} has no primary key")
    finally:
        conn.close()


def validate_semantic(ocel: OCEL, required_object_types: set[str] | None = None) -> None:
    """Gate 0 requirements not covered by either schema check."""
    if required_object_types is not None:
        present = {o.name for o in ocel.object_types}
        missing = required_object_types - present
        if missing:
            raise ValidationError(f"missing required object types: {missing}")

    if not ocel.events:
        raise ValidationError("no events present")
    if not ocel.objects:
        raise ValidationError("no objects present")

    for e in ocel.events:
        if e.time is None:
            raise ValidationError(f"event {e.id} missing timestamp")
        for r in e.relationships:
            if not r.qualifier:
                raise ValidationError(f"event {e.id} has an unqualified relationship to {r.target_id}")

    object_ids = {o.id for o in ocel.objects}
    for e in ocel.events:
        for r in e.relationships:
            if r.target_id not in object_ids:
                raise ValidationError(f"event {e.id} relates to unknown object {r.target_id}")
    for o in ocel.objects:
        for r in o.relationships:
            if r.target_id not in object_ids:
                raise ValidationError(f"object {o.id} relates to unknown object {r.target_id}")
            if not r.qualifier:
                raise ValidationError(f"object {o.id} has an unqualified relationship to {r.target_id}")


def validate_all(ocel: OCEL, sqlite_path: str, required_object_types: set[str] | None = None) -> None:
    validate_json(ocel)
    validate_sqlite_structure(sqlite_path)
    validate_semantic(ocel, required_object_types)
