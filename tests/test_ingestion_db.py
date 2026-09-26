from satsa.ingestion.adapters.db_adapter import DBAdapter

FIXTURE = "data/samples/cse_c_sqlite/cse_c.sqlite"


def test_discover_schema_reads_real_columns():
    adapter = DBAdapter(FIXTURE)
    schema = adapter.discover_schema()
    assert schema["cases"] == ["case_id", "handler", "team", "status", "opened_at", "closed_at"]


def test_fetch_records_returns_every_row():
    adapter = DBAdapter(FIXTURE)
    rows = adapter.fetch_records("cases")
    assert len(rows) == 2
    assert rows[0]["case_id"] == "CASE-C1"


def test_non_canonical_table_names_are_ignored_not_queried():
    """A real export's DB may contain other application tables — only tables whose
    name matches the canonical set are ever touched, and never via unvalidated SQL."""
    adapter = DBAdapter(FIXTURE)
    assert "sqlite_sequence" not in adapter.discover_schema()
