"""JSON adapter — same table set as CSVAdapter, each file a JSON array of objects."""
from __future__ import annotations

import json
from pathlib import Path
from typing import IO

from satsa.ingestion.adapters.base import SourceAdapter
from satsa.ingestion.schema import ALL_TABLES


class JSONAdapter(SourceAdapter):
    def __init__(self, sources: dict[str, str | IO]):
        self._sources = sources

    @classmethod
    def from_directory(cls, directory: str) -> "JSONAdapter":
        sources = {}
        for path in Path(directory).glob("*.json"):
            if path.stem in ALL_TABLES:
                sources[path.stem] = str(path)
        return cls(sources)

    def _rows(self, table: str) -> list[dict]:
        if table not in self._sources:
            return []
        source = self._sources[table]
        if isinstance(source, str):
            with open(source, encoding="utf-8") as f:
                data = json.load(f)
        else:
            source.seek(0)
            data = json.loads(source.read())
        if not isinstance(data, list):
            raise ValueError(f"{table}: expected a JSON array of records, got {type(data).__name__}")
        return data

    def discover_schema(self) -> dict[str, list[str]]:
        return {table: list(rows[0].keys()) if (rows := self._rows(table)) else [] for table in self._sources}

    def fetch_records(self, table: str) -> list[dict]:
        return self._rows(table)
