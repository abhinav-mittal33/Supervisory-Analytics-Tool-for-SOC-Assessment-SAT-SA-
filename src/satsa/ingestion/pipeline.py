"""Orchestrates one CSE's ingestion end to end: adapter -> field mapping -> quality
gate -> canonical OCEL build. The quality gate runs before OCEL construction so a
hard failure (missing required field) never reaches the OCEL builder with bad data —
matches the architecture diagram's own "ingestion -> data-reliability/ABSTAIN gate"
ordering (docs/architecture.md).
"""
from __future__ import annotations

from satsa.ingestion.adapters.base import SourceAdapter
from satsa.ingestion.mapping.field_mapper import FieldMapping, apply_all
from satsa.ingestion.normalization.canonical import build_ocel
from satsa.ingestion.quality.validator import IngestionReport, validate
from satsa.ingestion.schema import ALL_TABLES
from satsa.ocel.model import OCEL


def run_ingestion(
    adapter: SourceAdapter, mapping: FieldMapping, cse_id: str
) -> tuple[OCEL | None, IngestionReport]:
    raw_tables = {table: adapter.fetch_records(table) for table in ALL_TABLES}
    mapped_tables = apply_all(raw_tables, mapping)

    report = validate(mapped_tables)
    if report.status == "ABSTAIN":
        return None, report

    return build_ocel(mapped_tables, cse_id), report
