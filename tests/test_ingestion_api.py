"""Tested only against a local, in-process HTTP server — never a real external
endpoint, matching the offline-deployment mandate (docs/assumptions.md)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from satsa.ingestion.adapters.api_adapter import APIAdapter

_CASES = [{"case_id": "C1", "assigned_to": "ANL1"}]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/cases":
            body = json.dumps(_CASES).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()


def test_fetch_records_from_local_server(local_server):
    adapter = APIAdapter(local_server)
    assert adapter.fetch_records("cases") == _CASES


def test_missing_resource_returns_empty_not_an_error(local_server):
    adapter = APIAdapter(local_server)
    assert adapter.fetch_records("assets") == []


def test_rejects_non_http_scheme():
    with pytest.raises(ValueError):
        APIAdapter("file:///etc/passwd")
