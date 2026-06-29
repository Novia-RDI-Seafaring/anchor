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


def test_delete_workspace_removes_it_from_list():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "scratch"})
    rsp = client.delete("/api/workspaces/scratch")
    assert rsp.status_code == 200
    assert rsp.json() == {"slug": "scratch", "deleted": True}
    slugs = {w["slug"] for w in client.get("/api/workspaces").json()}
    assert "scratch" not in slugs
    missing = client.delete("/api/workspaces/scratch")
    assert missing.status_code == 404


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


def test_list_placeholders_returns_flagged_nodes():
    """Mirrors canvas_list_placeholders MCP tool. Adapter parity rule."""
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={
        "id": "ph", "node_type": "spec", "label": "Max pressure",
        "data": {"placeholder": True, "placeholder_hint": "Max inlet pressure"},
    })
    client.post("/api/workspaces/w1/nodes", json={
        "id": "filled", "node_type": "spec", "label": "Temp",
        "data": {"rows": [{"key": "k", "value": "v"}]},
    })
    rsp = client.get("/api/workspaces/w1/placeholders")
    assert rsp.status_code == 200
    body = rsp.json()
    assert {it["id"] for it in body} == {"ph"}
    assert body[0]["hint"] == "Max inlet pressure"
    assert body[0]["node_type"] == "spec"


def test_list_placeholders_empty():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    rsp = client.get("/api/workspaces/w1/placeholders")
    assert rsp.status_code == 200
    assert rsp.json() == []


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


def test_organize_subtree_direction_incoming_scopes_to_reports_to():
    """Reports-to convention: child → parent edge. Organising from m1
    with direction="incoming" walks arrows backward, so the m1 reports
    move but the CEO above does NOT."""
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "ceo", "x": 0, "y": 0})
    client.post("/api/workspaces/w1/nodes", json={"id": "m1", "x": 0, "y": 0})
    client.post("/api/workspaces/w1/nodes", json={"id": "r1", "x": -99, "y": -99})
    client.post("/api/workspaces/w1/nodes", json={"id": "r2", "x": 99, "y": 99})
    # reports-to: subordinate points at boss.
    client.post("/api/workspaces/w1/edges", json={"source": "m1", "target": "ceo"})
    client.post("/api/workspaces/w1/edges", json={"source": "r1", "target": "m1"})
    client.post("/api/workspaces/w1/edges", json={"source": "r2", "target": "m1"})

    rsp = client.post(
        "/api/workspaces/w1/layout",
        json={"root_id": "m1", "direction": "incoming"},
    )
    assert rsp.status_code == 200
    moved = {m["id"] for m in rsp.json()["moves"]}
    # CEO is NOT in the move set; only m1's reports.
    assert moved == {"r1", "r2"}


def test_organize_subtree_direction_default_is_any():
    """Omitting `direction` reproduces the v1 undirected walk — both
    directions of arrows are followed."""
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "ceo", "x": 0, "y": 0})
    client.post("/api/workspaces/w1/nodes", json={"id": "m1", "x": 0, "y": 0})
    client.post("/api/workspaces/w1/nodes", json={"id": "r1", "x": -99, "y": -99})
    client.post("/api/workspaces/w1/edges", json={"source": "m1", "target": "ceo"})
    client.post("/api/workspaces/w1/edges", json={"source": "r1", "target": "m1"})

    rsp = client.post(
        "/api/workspaces/w1/layout",
        json={"root_id": "m1"},
    )
    assert rsp.status_code == 200
    moved = {m["id"] for m in rsp.json()["moves"]}
    # CEO IS in the set under "any" — the historical (buggy-for-org-charts)
    # but no-surprise default behaviour.
    assert moved == {"ceo", "r1"}


def test_organize_subtree_bad_direction_400():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "r"})
    rsp = client.post(
        "/api/workspaces/w1/layout",
        json={"root_id": "r", "direction": "sideways"},
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


def test_patch_node_pure_parent_emits_reparented_event():
    """`PATCH /nodes/{id}` with only `{parent: <id>}` dispatches `reparent_node`
    and emits a `NodeReparented` event (not a generic `NodeUpdated`)."""
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "area", "node_type": "area"})
    client.post("/api/workspaces/w1/nodes", json={"id": "child", "node_type": "concept"})
    rsp = client.patch("/api/workspaces/w1/nodes/child", json={"parent": "area"})
    assert rsp.status_code == 200
    assert rsp.json()["event"]["type"] == "NodeReparented"
    state = client.get("/api/workspaces/w1/state").json()
    child = next(n for n in state["nodes"] if n["id"] == "child")
    assert child["parent"] == "area"


def test_patch_node_explicit_null_parent_unparents():
    """`PATCH /nodes/{id}` with `{parent: null}` detaches the node — the wire
    distinguishes "field omitted" (no-op) from "field set to null" (unparent)."""
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "area", "node_type": "area"})
    client.post(
        "/api/workspaces/w1/nodes",
        json={"id": "child", "node_type": "concept", "parent": "area"},
    )
    rsp = client.patch("/api/workspaces/w1/nodes/child", json={"parent": None})
    assert rsp.status_code == 200
    assert rsp.json()["event"]["type"] == "NodeReparented"
    state = client.get("/api/workspaces/w1/state").json()
    child = next(n for n in state["nodes"] if n["id"] == "child")
    assert child["parent"] is None


def test_patch_node_rejects_self_parent():
    """A node can't be its own parent — the route guards before dispatch."""
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a"})
    rsp = client.patch("/api/workspaces/w1/nodes/a", json={"parent": "a"})
    assert rsp.status_code == 400


# ── Node-write API hardening (#186/#189/#191/#192) ──────────────────────────

def test_http_add_node_type_alias_and_position():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    # `type` alias accepted; no x/y -> auto-place returns origin first.
    rsp = client.post("/api/workspaces/w1/nodes", json={"type": "fact", "id": "a"})
    assert rsp.status_code == 201, rsp.text
    body = rsp.json()
    assert body["event"]["payload"]["node_type"] == "fact"
    assert "position" in body


def test_http_add_node_auto_place_non_overlapping():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    b1 = client.post("/api/workspaces/w1/nodes", json={"node_type": "fact", "width": 120, "height": 80}).json()
    b2 = client.post("/api/workspaces/w1/nodes", json={"node_type": "fact", "width": 120, "height": 80}).json()
    assert b1["position"] != b2["position"]


def test_http_add_node_warns_on_dead_data_key():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    rsp = client.post("/api/workspaces/w1/nodes", json={
        "node_type": "fact", "x": 0, "y": 0, "data": {"body": "nope"},
    })
    assert "warning" in rsp.json()


def test_http_update_node_data_merges():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={
        "id": "a", "node_type": "fact", "x": 0, "y": 0,
        "data": {"text": "x", "source_ref": {"page": 1}},
    })
    rsp = client.patch("/api/workspaces/w1/nodes/a", json={"data": {"text": "y"}})
    assert rsp.status_code == 200, rsp.text
    node = next(n for n in rsp.json()["state"]["nodes"] if n["id"] == "a")
    assert node["data"]["text"] == "y"
    assert node["data"]["source_ref"] == {"page": 1}


def test_http_node_types_route():
    client, _ = _client()
    rsp = client.get("/api/node-types")
    assert rsp.status_code == 200
    names = {e["name"] for e in rsp.json()}
    assert {"fact", "concept"} <= names
    one = client.get("/api/node-types/fact")
    assert one.status_code == 200
    assert one.json()["body_field"] == "text"
    assert client.get("/api/node-types/nope").status_code == 404


def test_http_add_edge_type_alias():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post("/api/workspaces/w1/nodes", json={"id": "a", "x": 0, "y": 0})
    client.post("/api/workspaces/w1/nodes", json={"id": "b", "x": 200, "y": 0})
    rsp = client.post("/api/workspaces/w1/edges", json={
        "source": "a", "target": "b", "type": "anchored",
        "data": {"kind": "evidence", "source_ref": {"page": 1}},
    })
    assert rsp.status_code == 201, rsp.text
    assert rsp.json()["event"]["payload"]["edge_type"] == "anchored"


def test_http_reference_create_list_attach_roundtrip():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    client.post(
        "/api/workspaces/w1/nodes",
        json={"id": "n1", "node_type": "fact", "x": 0, "y": 0},
    )
    # create
    created = client.post(
        "/api/workspaces/w1/references",
        json={
            "source_ref": {"slug": "datasheet", "page": 3, "bbox": [1, 2, 3, 4]},
            "label": "Max inlet pressure",
        },
    )
    assert created.status_code == 201, created.text
    ref = created.json()
    assert ref["id"]
    assert ref["label"] == "Max inlet pressure"
    # list
    listed = client.get("/api/workspaces/w1/references")
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [ref["id"]]
    # attach
    attached = client.post(
        f"/api/workspaces/w1/references/{ref['id']}/attach",
        json={"node_id": "n1"},
    )
    assert attached.status_code == 200, attached.text
    state = attached.json()["state"]
    node = next(n for n in state["nodes"] if n["id"] == "n1")
    assert node["data"]["reference_id"] == ref["id"]
    assert node["data"]["source_ref"]["slug"] == "datasheet"


def test_http_reference_rejects_malformed_source_ref():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    rsp = client.post("/api/workspaces/w1/references", json={"source_ref": {"page": 3}})
    assert rsp.status_code == 400


def test_http_reference_list_backward_compatible():
    client, _ = _client()
    client.post("/api/workspaces", json={"slug": "w1"})
    rsp = client.get("/api/workspaces/w1/references")
    assert rsp.status_code == 200
    assert rsp.json() == []
