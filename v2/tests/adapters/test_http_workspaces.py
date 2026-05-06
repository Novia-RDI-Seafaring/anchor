"""HTTP adapter — workspace + node + edge end-to-end."""
from __future__ import annotations

from fastapi.testclient import TestClient

from anchor.adapters.http.app import build_app

from tests.fixtures.services import make_in_memory_services


def _client():
    s = make_in_memory_services()
    app = build_app(
        workspace_service=s.workspace,
        ingest_service=s.ingest,
        doc_store=s.doc_store,
        bus=s.bus,
    )
    return TestClient(app), s


def test_create_and_list_workspaces():
    client, _ = _client()
    rsp = client.post("/api/workspaces", json={"slug": "w1", "title": "One"})
    assert rsp.status_code == 201
    assert rsp.json()["slug"] == "w1"
    rsp2 = client.get("/api/workspaces")
    assert rsp2.status_code == 200
    assert any(w["slug"] == "w1" for w in rsp2.json())


def test_add_node_and_get_state():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    rsp = client.post("/api/workspaces/w1/nodes", json={"id": "a", "label": "A"})
    assert rsp.status_code == 201
    body = rsp.json()
    assert body["event"]["type"] == "NodeAdded"
    state = client.get("/api/workspaces/w1/state").json()
    assert any(n["id"] == "a" for n in state["nodes"])


def test_add_edge_rejects_orphan_endpoint():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a"})
    rsp = client.post("/api/workspaces/w1/edges", json={"source": "a", "target": "ghost"})
    assert rsp.status_code == 400


def test_delete_node_cascades_edges():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a"})
    client.post("/api/workspaces/w1/nodes", json={"id": "b"})
    e_rsp = client.post("/api/workspaces/w1/edges", json={"id": "e", "source": "a", "target": "b"})
    assert e_rsp.status_code == 201
    rsp = client.delete("/api/workspaces/w1/nodes/a")
    assert rsp.status_code == 200
    types = [e["type"] for e in rsp.json()["events"]]
    assert types == ["EdgeRemoved", "NodeRemoved"]


def test_move_node_via_patch():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a"})
    rsp = client.patch("/api/workspaces/w1/nodes/a", json={"x": 100, "y": 200})
    assert rsp.status_code == 200
    assert rsp.json()["event"]["type"] == "NodeMoved"
