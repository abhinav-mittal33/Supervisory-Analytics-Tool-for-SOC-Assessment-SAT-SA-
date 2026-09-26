"""The real proof, not just 'no exception thrown': three deliberately heterogeneous
CSE exports (CSV / JSON / SQLite database export), each with its own column names,
normalize into the same canonical vocabulary and the existing Moat 1 fusion pipeline
(unmodified) actually recovers a planted reassignment loop from real-shaped CSV data.
"""
from satsa.ingestion.adapters.csv_adapter import CSVAdapter
from satsa.ingestion.adapters.db_adapter import DBAdapter
from satsa.ingestion.adapters.json_adapter import JSONAdapter
from satsa.ingestion.pipeline import run_ingestion
from satsa.ingestion.schema import ALL_TABLES, suggest_mapping
from satsa.moat1.fusion import fuse
from satsa.moat1.structural import detect_reassignment_loops
from satsa.ocel import sqlite_io
from satsa.okf import compiler


def _auto_mapping(adapter, overrides=None):
    overrides = overrides or {}
    schema = adapter.discover_schema()
    mapping = {}
    for table in ALL_TABLES:
        columns = schema.get(table, [])
        guess = suggest_mapping(table, columns)
        guess.update(overrides.get(table, {}))
        mapping[table] = guess
    return mapping


def test_csv_cse_ingests_and_recovers_the_planted_reassignment_loop():
    adapter = CSVAdapter.from_directory("data/samples/cse_a_csv")
    ocel, report = run_ingestion(adapter, _auto_mapping(adapter), cse_id="CSE_A")
    assert report.status == "OK"
    signals = detect_reassignment_loops(ocel)
    flagged = [s for s in signals if s.flagged]
    assert any(s.case_id == "CASE001" for s in flagged)


def test_json_cse_with_different_column_names_ingests_successfully():
    adapter = JSONAdapter.from_directory("data/samples/cse_b_json")
    ocel, report = run_ingestion(adapter, _auto_mapping(adapter), cse_id="CSE_B")
    assert report.status == "OK"
    assert any(o.type == "Case" for o in ocel.objects)


def test_sqlite_cse_needs_manual_override_for_non_aliased_columns():
    adapter = DBAdapter("data/samples/cse_c_sqlite/cse_c.sqlite")
    overrides = {"cases": {"analyst_id": "handler", "queue_id": "team"}}
    ocel, report = run_ingestion(adapter, _auto_mapping(adapter, overrides), cse_id="CSE_C")
    assert report.status == "OK"
    case = next(o for o in ocel.objects if o.id == "CASE-C1")
    assert any(r.qualifier == "current_assignee" and r.target_id == "A.Kumar" for r in case.relationships)


def test_ingested_ocel_feeds_the_same_okf_fusion_pipeline_unmodified(tmp_path):
    adapter = CSVAdapter.from_directory("data/samples/cse_a_csv")
    ocel, report = run_ingestion(adapter, _auto_mapping(adapter), cse_id="CSE_A")
    assert report.status == "OK"

    sqlite_path = str(tmp_path / "cse_a.sqlite")
    sqlite_io.write_sqlite(ocel, sqlite_path)
    conn = compiler.connect(sqlite_path)
    result = fuse(ocel, conn)
    assert any(c.finding_type == "REASSIGNMENT_LOOP" for c in result.concerns)
