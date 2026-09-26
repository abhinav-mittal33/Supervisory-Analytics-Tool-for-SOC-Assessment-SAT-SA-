from satsa.ingestion.adapters.json_adapter import JSONAdapter
from satsa.ingestion.schema import suggest_mapping

FIXTURE = "data/samples/cse_b_json"


def test_discover_schema_reads_json_keys():
    adapter = JSONAdapter.from_directory(FIXTURE)
    schema = adapter.discover_schema()
    assert "incident_number" in schema["cases"]


def test_fetch_records_returns_every_record():
    adapter = JSONAdapter.from_directory(FIXTURE)
    rows = adapter.fetch_records("case_events")
    assert len(rows) == 4


def test_auto_suggest_maps_incident_number_and_owner_without_override():
    adapter = JSONAdapter.from_directory(FIXTURE)
    columns = adapter.discover_schema()["cases"]
    guess = suggest_mapping("cases", columns)
    assert guess["case_id"] == "incident_number"
    assert guess["analyst_id"] == "owner"
    assert guess["queue_id"] == "queue"


def test_non_list_json_raises_value_error(tmp_path):
    bad = tmp_path / "cases.json"
    bad.write_text('{"not": "a list"}')
    adapter = JSONAdapter({"cases": str(bad)})
    try:
        adapter.fetch_records("cases")
        assert False, "expected ValueError"
    except ValueError:
        pass
