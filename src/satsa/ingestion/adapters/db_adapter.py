"""SQLite database-export adapter — covers the "database exports" input class.
Read-only connection; table names are matched against the canonical table set
before ever being interpolated into SQL, so nothing from `sqlite_master` reaches a
query string unchecked (Database rules: no string concatenation with unvalidated
identifiers)."""
from __future__ import annotations

import sqlite3

from satsa.ingestion.adapters.base import SourceAdapter
from satsa.ingestion.schema import ALL_TABLES


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class DBAdapter(SourceAdapter):
    def __init__(self, path: str):
        # uri=True + mode=ro: refuses to open anything but an existing file read-only —
        # a corrupted/missing upload fails loudly here, not deep inside a query.
        self._conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row
        self._tables = {
            row["name"]
            for row in self._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            if row["name"] in ALL_TABLES
        }

    def discover_schema(self) -> dict[str, list[str]]:
        schema = {}
        for table in self._tables:
            cols = [c[1] for c in self._conn.execute(f"PRAGMA table_info({_q(table)})").fetchall()]
            schema[table] = cols
        return schema

    def fetch_records(self, table: str) -> list[dict]:
        if table not in self._tables:
            return []
        rows = self._conn.execute(f"SELECT * FROM {_q(table)}").fetchall()
        return [dict(r) for r in rows]
