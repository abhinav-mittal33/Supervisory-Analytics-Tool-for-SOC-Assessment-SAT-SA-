"""SourceAdapter interface — every ingestion source (CSV, JSON, DB export, API)
implements the same two methods, so `pipeline.py` and the UI never branch on
source type after construction."""
from __future__ import annotations

from abc import ABC, abstractmethod


class SourceAdapter(ABC):
    @abstractmethod
    def discover_schema(self) -> dict[str, list[str]]:
        """table/resource name -> detected column names, read directly from the
        source (CSV header row, JSON object keys, DB PRAGMA, API sample record) —
        never assumed."""

    @abstractmethod
    def fetch_records(self, table: str) -> list[dict]:
        """Raw rows for one table/resource, as-is — field mapping happens later,
        in mapping/field_mapper.py, not here."""
