"""CSV adapter — one file per canonical table (cases.csv, case_events.csv, and
optionally alerts.csv/assets.csv/analysts.csv/queues.csv). Different CSEs use
different column names inside each file; that's `mapping/field_mapper.py`'s job,
not this adapter's."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import IO

from satsa.ingestion.adapters.base import SourceAdapter
from satsa.ingestion.schema import ALL_TABLES


class CSVAdapter(SourceAdapter):
    def __init__(self, sources: dict[str, str | IO]):
        """sources: canonical table name -> file path or an open file-like object
        (Streamlit's UploadedFile satisfies the latter)."""
        self._sources = sources

    @classmethod
    def from_directory(cls, directory: str) -> "CSVAdapter":
        """Convenience for fixtures/tests: maps every *.csv file's stem to a table
        name (cases.csv -> 'cases'), skipping anything not in the canonical table
        set rather than guessing what an unrecognized file might mean."""
        sources = {}
        for path in Path(directory).glob("*.csv"):
            if path.stem in ALL_TABLES:
                sources[path.stem] = str(path)
        return cls(sources)

    def _rows(self, table: str) -> list[dict]:
        if table not in self._sources:
            return []
        source = self._sources[table]
        if isinstance(source, str):
            with open(source, newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        source.seek(0)
        text = source.read()
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        return list(csv.DictReader(text.splitlines()))

    def discover_schema(self) -> dict[str, list[str]]:
        return {table: list(rows[0].keys()) if (rows := self._rows(table)) else [] for table in self._sources}

    def fetch_records(self, table: str) -> list[dict]:
        return self._rows(table)
