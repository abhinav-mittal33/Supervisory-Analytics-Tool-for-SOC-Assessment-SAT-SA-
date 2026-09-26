"""Regenerates data/samples/cse_c_sqlite/cse_c.sqlite — the third of the three
deliberately heterogeneous demo CSE exports (CSV / JSON / SQLite database export)
proving the ingestion layer normalizes all three into one canonical model. Unlike
data/dev and data/scaled, this fixture IS committed (it's a small, static demo
input, not large derived data) — this script exists purely so it's reproducible
rather than a hand-edited binary.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "samples" / "cse_c_sqlite" / "cse_c.sqlite"


def build() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.unlink(missing_ok=True)
    conn = sqlite3.connect(OUT)
    conn.execute("CREATE TABLE cases (case_id TEXT, handler TEXT, team TEXT, status TEXT, opened_at TEXT, closed_at TEXT)")
    conn.execute("CREATE TABLE case_events (case_id TEXT, event TEXT, actor TEXT, ts TEXT)")
    conn.executemany(
        "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("CASE-C1", "A.Kumar", "Tier1", "OPEN", "2026-03-01T08:00:00Z", "2026-03-01T09:00:00Z"),
            ("CASE-C2", "B.Mehta", "Tier2", "OPEN", "2026-03-01T08:10:00Z", "2026-03-01T08:40:00Z"),
        ],
    )
    conn.executemany(
        "INSERT INTO case_events VALUES (?, ?, ?, ?)",
        [
            ("CASE-C1", "investigate", "A.Kumar", "2026-03-01T08:20:00Z"),
            ("CASE-C1", "closed", None, "2026-03-01T09:00:00Z"),
            ("CASE-C2", "reassigned", "C.Nair", "2026-03-01T08:15:00Z"),
            ("CASE-C2", "closed", None, "2026-03-01T08:40:00Z"),
        ],
    )
    conn.commit()
    conn.close()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
