from __future__ import annotations

from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app
from anchor.infra.config import AnchorConfig
from tests.fixtures.services import make_in_memory_services


def test_http_status_reports_shared_counts(tmp_path):
    services = make_in_memory_services()
    app = build_app(
        workspace_service=services.workspace,
        ingest_service=services.ingest,
        doc_store=services.doc_store,
        bus=services.bus,
        config=AnchorConfig(data_dir=tmp_path / "anchor-data"),
    )
    client = TestClient(app)

    client.post("/api/workspaces", json={"slug": "w1"})
    services.doc_store.seed_document("pump", filename="pump.pdf", page_count=4)

    response = client.get("/api/status")

    assert response.status_code == 200
    body = response.json()
    assert body["data_dir"]["path"] == str(tmp_path / "anchor-data")
    assert body["counts"]["workspaces"] == 1
    assert body["counts"]["documents"] == 1
    assert body["config"]["source"] in {
        "ANCHOR_CONFIG",
        "cwd-search",
        "environment-or-defaults",
    }
