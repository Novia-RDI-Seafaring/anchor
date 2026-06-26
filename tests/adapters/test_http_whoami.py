"""`GET /api/whoami` reports the bound env/project + the real host:port.

The server self-identifies so an agent never assumes localhost:8002 is its
project (#177, #179).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from anchor.infra.config import AnchorConfig
from tests.fixtures.services import make_in_memory_services


def _client(tmp_path, **state):
    services = make_in_memory_services()
    app = build_app(
        workspace_service=services.workspace,
        ingest_service=services.ingest,
        doc_store=services.doc_store,
        bus=services.bus,
        config=AnchorConfig(data_dir=tmp_path / "anchor-data"),
    )
    for key, value in state.items():
        setattr(app.state, key, value)
    return TestClient(app)


def test_whoami_uses_serve_binding_port(tmp_path):
    client = _client(tmp_path, serve_binding={
        "host": "127.0.0.1",
        "port": 8004,
        "data_dir": str(tmp_path / "anchor-data"),
        "env": "work",
        "project": "pumps",
        "started_at": "2026-06-26T00:00:00Z",
    })
    body = client.get("/api/whoami").json()
    assert body["env"] == "work"
    assert body["project"] == "pumps"
    assert body["port"] == 8004  # not the default 8002
    assert body["base_url"] == "http://127.0.0.1:8004"
    assert body["canvas_url_prefix"] == "http://127.0.0.1:8004/c/"


def test_whoami_rewrites_wildcard_host(tmp_path):
    client = _client(tmp_path, serve_binding={
        "host": "0.0.0.0",
        "port": 8006,
        "data_dir": str(tmp_path / "anchor-data"),
        "env": None,
        "project": None,
        "started_at": None,
    })
    body = client.get("/api/whoami").json()
    assert body["base_url"] == "http://127.0.0.1:8006"


def test_whoami_falls_back_to_config_without_binding(tmp_path):
    # Built without `anchor serve` (e.g. embedded): report the config port.
    client = _client(tmp_path)
    body = client.get("/api/whoami").json()
    assert body["port"] == 8002
    assert body["data_dir"] == str(tmp_path / "anchor-data")
