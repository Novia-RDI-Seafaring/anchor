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
    body = rsp2.json()
    assert any(w["slug"] == "w1" for w in body)
    # Envelope now carries counts + ref graph so the landing-page folder
    # tree and the canvas_list_workspaces MCP tool see the same shape.
    entry = next(w for w in body if w["slug"] == "w1")
    assert entry["node_count"] == 0
    assert entry["edge_count"] == 0
    assert entry["references"] == []
    assert entry["referenced_by"] == []


def test_list_workspaces_envelope_reflects_sub_canvas_link():
    """After create_sub_canvas, parent.references and child.referenced_by line up."""
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "plant"})
    client.post(
        "/api/workspaces/plant/sub-canvas",
        json={"slug": "pump", "title": "Pump"},
    )
    items = {w["slug"]: w for w in client.get("/api/workspaces").json()}
    assert items["plant"]["references"] == ["pump"]
    assert items["pump"]["referenced_by"] == ["plant"]
    # The linking canvas-node lifts plant's node_count to 1.
    assert items["plant"]["node_count"] == 1
    assert items["pump"]["node_count"] == 0


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


def test_organize_subtree_returns_moves():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    # Tiny tree: r → {a, b}.
    client.post("/api/workspaces/w1/nodes", json={"id": "r"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a", "x": -99, "y": -99})
    client.post("/api/workspaces/w1/nodes", json={"id": "b", "x": 99, "y": 99})
    client.post("/api/workspaces/w1/edges", json={"source": "a", "target": "r"})
    client.post("/api/workspaces/w1/edges", json={"source": "b", "target": "r"})
    rsp = client.post(
        "/api/workspaces/w1/layout",
        json={"root_id": "r", "orientation": "vertical"},
    )
    assert rsp.status_code == 200
    body = rsp.json()
    moved = {m["id"] for m in body["moves"]}
    assert moved == {"a", "b"}
    assert body["event_count"] == 2


def test_organize_subtree_unknown_root_400():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    rsp = client.post(
        "/api/workspaces/w1/layout",
        json={"root_id": "ghost"},
    )
    assert rsp.status_code == 400


def test_align_returns_moves():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a", "x": 0,  "y": 0,  "width": 100, "height": 100})
    client.post("/api/workspaces/w1/nodes", json={"id": "b", "x": 50, "y": 30, "width": 100, "height": 100})
    rsp = client.post(
        "/api/workspaces/w1/align",
        json={"ids": ["a", "b"], "anchor": "top"},
    )
    assert rsp.status_code == 200
    body = rsp.json()
    moved = {m["id"] for m in body["moves"]}
    assert moved == {"b"}
    assert body["event_count"] == 1


def test_align_unknown_node_400():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a"})
    rsp = client.post(
        "/api/workspaces/w1/align",
        json={"ids": ["a", "ghost"], "anchor": "top"},
    )
    assert rsp.status_code == 400


def test_distribute_returns_moves():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a", "x": 0,   "width": 100, "height": 100})
    client.post("/api/workspaces/w1/nodes", json={"id": "b", "x": 120, "width": 100, "height": 100})
    client.post("/api/workspaces/w1/nodes", json={"id": "c", "x": 300, "width": 100, "height": 100})
    rsp = client.post(
        "/api/workspaces/w1/distribute",
        json={"ids": ["a", "b", "c"], "axis": "horizontal"},
    )
    assert rsp.status_code == 200
    body = rsp.json()
    moved = {m["id"] for m in body["moves"]}
    assert moved == {"b"}


def test_distribute_too_few_400():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a"})
    client.post("/api/workspaces/w1/nodes", json={"id": "b"})
    rsp = client.post(
        "/api/workspaces/w1/distribute",
        json={"ids": ["a", "b"], "axis": "horizontal"},
    )
    assert rsp.status_code == 400


def test_create_sub_canvas_happy_path():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "plant"})
    rsp = client.post(
        "/api/workspaces/plant/sub-canvas",
        json={"slug": "pump-loop", "title": "Pump Loop", "x": 10, "y": 20},
    )
    assert rsp.status_code == 201
    body = rsp.json()
    assert body["child"]["slug"] == "pump-loop"
    assert body["node"]["node_type"] == "canvas"
    assert body["node"]["data"]["canvas_slug"] == "pump-loop"
    assert body["event"]["type"] == "NodeAdded"
    # Child workspace shows up in /api/workspaces.
    listed = {w["slug"] for w in client.get("/api/workspaces").json()}
    assert {"plant", "pump-loop"} <= listed
    # Linking node lives on the parent.
    parent_state = client.get("/api/workspaces/plant/state").json()
    canvas_nodes = [n for n in parent_state["nodes"] if n["node_type"] == "canvas"]
    assert len(canvas_nodes) == 1
    assert canvas_nodes[0]["data"]["canvas_slug"] == "pump-loop"


def test_create_sub_canvas_rejects_self_link():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "plant"})
    rsp = client.post(
        "/api/workspaces/plant/sub-canvas", json={"slug": "plant"},
    )
    assert rsp.status_code == 400
