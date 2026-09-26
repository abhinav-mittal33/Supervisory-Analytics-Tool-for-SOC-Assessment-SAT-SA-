import time

from satsa.ingestion.schema import ALL_TABLES, suggest_mapping
from satsa.ingestion.adapters.csv_adapter import CSVAdapter
from satsa.portfolio import history as portfolio_history
from satsa.ui import background


def _wait_for(job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = background.get_job_status(job_id)
        if status.status != "running":
            return status
        time.sleep(0.05)
    raise TimeoutError(f"job {job_id} did not finish in {timeout}s")


def test_ingestion_job_runs_in_background_and_records_a_real_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio_history, "HISTORY_DIR", tmp_path)
    sources = {
        "cases": "data/samples/cse_a_csv/cases.csv",
        "case_events": "data/samples/cse_a_csv/case_events.csv",
        "alerts": "data/samples/cse_a_csv/alerts.csv",
        "assets": "data/samples/cse_a_csv/assets.csv",
    }
    adapter = CSVAdapter(sources)
    mapping = {t: suggest_mapping(t, adapter.discover_schema().get(t, [])) for t in ALL_TABLES}

    job_id = background.start_ingestion_job("CSE_BG_TEST", "CSV", sources, mapping)
    status = _wait_for(job_id)

    assert status.status == "done"
    assert status.error is None
    records = portfolio_history.list_submissions("CSE_BG_TEST")
    assert len(records) == 1
    assert records[0].case_count == 3


def test_ingestion_job_reports_error_status_not_a_crashed_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio_history, "HISTORY_DIR", tmp_path)
    sources = {"cases": "data/samples/cse_a_csv/cases.csv"}  # case_events missing -> ABSTAIN
    adapter = CSVAdapter(sources)
    mapping = {t: suggest_mapping(t, adapter.discover_schema().get(t, [])) for t in ALL_TABLES}

    job_id = background.start_ingestion_job("CSE_BG_ERR", "CSV", sources, mapping)
    status = _wait_for(job_id)

    assert status.status == "error"
    assert status.error


def test_forget_job_removes_it_from_the_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio_history, "HISTORY_DIR", tmp_path)
    sources = {
        "cases": "data/samples/cse_a_csv/cases.csv",
        "case_events": "data/samples/cse_a_csv/case_events.csv",
    }
    adapter = CSVAdapter(sources)
    mapping = {t: suggest_mapping(t, adapter.discover_schema().get(t, [])) for t in ALL_TABLES}
    job_id = background.start_ingestion_job("CSE_BG_TEST2", "CSV", sources, mapping)
    _wait_for(job_id)
    background.forget_job(job_id)
    status = background.get_job_status(job_id)
    assert status.status == "error"  # unknown job falls back to this
