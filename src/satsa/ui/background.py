"""Runs CSE ingestion in a background thread so importing new data never freezes
the rest of the app — an investigator can keep browsing every other entity while a
new submission is being processed. Standard library `threading` only, no new
dependency (Rule 4).

Design: the background thread NEVER touches `st.session_state` (unsafe across
threads) and never receives a live adapter built from Streamlit's own uploaded-file
objects or an open sqlite3 connection (also unsafe to share across threads) — the
caller must have already saved uploads to temp file paths on the main thread first.
The thread builds its OWN fresh adapter from those paths, runs the full
ingest -> fuse -> record_submission pipeline, and writes its result only to disk
(`portfolio_history.record_submission`) and to a plain module-level dict guarded by
a lock (safe: simple dict get/set is GIL-atomic). The UI polls that dict; new data
only ever appears once the job's status is "done" — never mid-write.
"""
from __future__ import annotations

import tempfile
import threading
import uuid
from dataclasses import dataclass

from satsa.ingestion.adapters.csv_adapter import CSVAdapter
from satsa.ingestion.adapters.db_adapter import DBAdapter
from satsa.ingestion.adapters.json_adapter import JSONAdapter
from satsa.ingestion.pipeline import run_ingestion
from satsa.moat1.fusion import fuse
from satsa.ocel import sqlite_io
from satsa.okf import compiler
from satsa.portfolio import history as portfolio_history

_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}


@dataclass(frozen=True)
class JobStatus:
    status: str  # "running" | "done" | "error"
    cse_id: str
    error: str | None = None


def _build_adapter(fmt: str, source_paths):
    if fmt == "CSV":
        return CSVAdapter(source_paths)
    if fmt == "JSON":
        return JSONAdapter(source_paths)
    return DBAdapter(source_paths)


def _run_job(job_id: str, cse_id: str, fmt: str, source_paths, mapping: dict) -> None:
    try:
        adapter = _build_adapter(fmt, source_paths)
        ocel, report = run_ingestion(adapter, mapping, cse_id)
        if ocel is None:
            error = "; ".join(report.errors) or "ingestion returned no data"
            with _LOCK:
                _JOBS[job_id] = {"status": "error", "cse_id": cse_id, "error": error}
            return

        sqlite_path = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False).name
        sqlite_io.write_sqlite(ocel, sqlite_path)
        conn = compiler.connect(sqlite_path)
        # Real provenance, not the synthetic-generator default — this is a real
        # examiner-uploaded CSV/JSON/SQLite file, and the evidence package's own
        # source_system field should say so, not silently claim "satsa-generator".
        source_system = type(adapter).__name__
        result = fuse(ocel, conn, cse_id=cse_id, low_confidence_cases=report.low_confidence_cases,
                       source_system=source_system)
        portfolio_history.record_submission(cse_id, ocel, result, note="Imported via UI", source_system=source_system)
        with _LOCK:
            _JOBS[job_id] = {"status": "done", "cse_id": cse_id, "error": None}
    except Exception as exc:  # noqa: BLE001 — surface any failure to the UI, never crash the thread silently
        with _LOCK:
            _JOBS[job_id] = {"status": "error", "cse_id": cse_id, "error": str(exc)}


def start_ingestion_job(cse_id: str, fmt: str, source_paths, mapping: dict) -> str:
    job_id = str(uuid.uuid4())
    with _LOCK:
        _JOBS[job_id] = {"status": "running", "cse_id": cse_id, "error": None}
    thread = threading.Thread(target=_run_job, args=(job_id, cse_id, fmt, source_paths, mapping), daemon=True)
    thread.start()
    return job_id


def get_job_status(job_id: str) -> JobStatus:
    with _LOCK:
        state = _JOBS.get(job_id, {"status": "error", "cse_id": "?", "error": "unknown job"})
    return JobStatus(**state)


def forget_job(job_id: str) -> None:
    with _LOCK:
        _JOBS.pop(job_id, None)
