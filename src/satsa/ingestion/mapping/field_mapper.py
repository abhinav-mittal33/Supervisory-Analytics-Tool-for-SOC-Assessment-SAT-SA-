"""Applies a confirmed per-table field mapping to raw adapter rows, producing rows
keyed by canonical field name. Auto-suggestion (schema.suggest_mapping) happens
before this — this function only ever sees a mapping the caller has confirmed."""
from __future__ import annotations

from satsa.ingestion.schema import TABLE_FIELDS

FieldMapping = dict[str, dict[str, str | None]]  # table -> canonical_field -> source_column


def apply(raw_rows: list[dict], mapping: dict[str, str | None]) -> list[dict]:
    """mapping here is one table's canonical_field -> source_column dict."""
    out = []
    for row in raw_rows:
        mapped = {}
        for field, source_column in mapping.items():
            if source_column is None:
                mapped[field] = None
            else:
                mapped[field] = row.get(source_column)
        out.append(mapped)
    return out


def apply_all(tables: dict[str, list[dict]], mapping: FieldMapping) -> dict[str, list[dict]]:
    return {
        table: apply(rows, mapping.get(table, {}))
        for table, rows in tables.items()
        if table in TABLE_FIELDS
    }
