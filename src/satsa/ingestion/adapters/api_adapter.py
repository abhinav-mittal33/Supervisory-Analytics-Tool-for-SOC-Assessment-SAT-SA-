"""Generic REST/JSON API adapter — covers "APIs where available" without building
per-vendor connectors (Splunk, ServiceNow, QRadar, ...). Assumes GET <base_url>/<table>
returns a JSON array of records, one canonical table per resource — the same shape a
CSE's own internal case-management API is most likely to already expose.

This is an examiner-configured connection to a CSE's own system, supplied at
ingestion time (base_url + optional token) — not a hardcoded external dependency and
not a call this build makes on its own initiative. See docs/assumptions.md for why
this doesn't violate the air-gapped/offline mandate: the automated
`tests/test_offline_deployment.py` proves the analytical core makes zero network
calls of its own; this adapter is the one component whose entire purpose is a
network call the *examiner* explicitly configures against their own SOC, and it is
tested only against a local, in-process HTTP server, never a real endpoint.
"""
from __future__ import annotations

import json
import urllib.request
from urllib.parse import urlsplit

from satsa.ingestion.adapters.base import SourceAdapter
from satsa.ingestion.schema import ALL_TABLES

_TIMEOUT_SECONDS = 10


class APIAdapter(SourceAdapter):
    def __init__(self, base_url: str, token: str | None = None):
        scheme = urlsplit(base_url).scheme
        if scheme not in ("http", "https"):
            raise ValueError(f"base_url must be http(s), got scheme {scheme!r}")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._cache: dict[str, list[dict] | None] = {}

    def _get(self, table: str) -> list[dict]:
        if table in self._cache:
            return self._cache[table] or []
        req = urllib.request.Request(f"{self._base_url}/{table}")
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read())
        except (OSError, ValueError):
            self._cache[table] = None
            return []
        if not isinstance(data, list):
            raise ValueError(f"{table}: expected a JSON array of records, got {type(data).__name__}")
        self._cache[table] = data
        return data

    def discover_schema(self) -> dict[str, list[str]]:
        schema = {}
        for table in ALL_TABLES:
            rows = self._get(table)
            if rows:
                schema[table] = list(rows[0].keys())
        return schema

    def fetch_records(self, table: str) -> list[dict]:
        return self._get(table)
