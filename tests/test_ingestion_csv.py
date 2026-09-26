from satsa.ingestion.adapters.csv_adapter import CSVAdapter
from satsa.ingestion.schema import suggest_mapping

FIXTURE = "data/samples/cse_a_csv"


def test_discover_schema_reads_real_headers():
    adapter = CSVAdapter.from_directory(FIXTURE)
    schema = adapter.discover_schema()
    assert schema["cases"] == ["case_id", "assigned_to", "assignment_group", "status", "opened_at", "closed_at", "alert_id"]


def test_fetch_records_returns_every_row():
    adapter = CSVAdapter.from_directory(FIXTURE)
    rows = adapter.fetch_records("cases")
    assert len(rows) == 3
    assert rows[0]["case_id"] == "CASE001"


def test_fetch_records_on_unknown_table_returns_empty_not_an_error():
    adapter = CSVAdapter.from_directory(FIXTURE)
    assert adapter.fetch_records("queues") == []


def test_auto_suggest_maps_assigned_to_to_analyst_id():
    adapter = CSVAdapter.from_directory(FIXTURE)
    columns = adapter.discover_schema()["cases"]
    guess = suggest_mapping("cases", columns)
    assert guess["analyst_id"] == "assigned_to"
    assert guess["queue_id"] == "assignment_group"
