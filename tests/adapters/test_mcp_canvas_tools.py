"""MCP canvas tool handlers — call directly without MCP transport."""
from __future__ import annotations

import asyncio
import json

from anchor.adapters.mcp import handlers_canvas
from anchor.adapters.mcp.server import _error_result
from tests.fixtures.services import make_in_memory_services


def test_canvas_create_and_add_node():
    async def run():
        s = make_in_memory_services()
        await handlers_canvas.call_tool(s.workspace, "canvas_create_workspace", {"slug": "w1"})
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_node", {
            "workspace_slug": "w1", "id": "a", "label": "A", "node_type": "concept",
        })
        out = json.loads(body)
        assert out["event"]["type"] == "NodeAdded"

    asyncio.run(run())


def test_canvas_get_state_returns_nodes_and_edges():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        body = await handlers_canvas.call_tool(s.workspace, "canvas_get_state", {"workspace_slug": "w1"})
        state = json.loads(body)
        assert state["nodes"][0]["id"] == "a"

    asyncio.run(run())


def test_canvas_remove_node_returns_cascade():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        await s.workspace.add_node("w1", id="b")
        await s.workspace.add_edge("w1", source="a", target="b")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_remove_node", {"workspace_slug": "w1", "id": "a"},
        )
        out = json.loads(body)
        assert [e["type"] for e in out["events"]] == ["EdgeRemoved", "NodeRemoved"]

    asyncio.run(run())


def test_unknown_tool_returns_json_error():
    async def run():
        s = make_in_memory_services()
        body = await handlers_canvas.call_tool(s.workspace, "canvas_bogus", {})
        assert "error" in json.loads(body)

    asyncio.run(run())


def test_mcp_error_result_is_valid_json_for_quoted_message():
    message = 'invalid "quoted" input at C:\\tmp\\fixture'
    assert json.loads(_error_result(ValueError(message))) == {"error": message}


def test_invalid_command_returns_json_error():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_edge", {
            "workspace_slug": "w1", "source": "ghost", "target": "ghost",
        })
        assert "error" in json.loads(body)

    asyncio.run(run())


def test_tool_definitions_have_required_fields():
    defs = handlers_canvas.tool_definitions()
    assert all("name" in d and "description" in d and "inputSchema" in d for d in defs)
    names = {d["name"] for d in defs}
    assert "canvas_get_state" in names and "canvas_add_node" in names
    # New: organize-subtree tool ships in this PR.
    assert "canvas_organize_subtree" in names


def test_canvas_delete_workspace_tool_is_registered_and_removes_workspace():
    names = {d["name"] for d in handlers_canvas.tool_definitions()}
    assert "canvas_delete_workspace" in names

    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("scratch")
        body = await handlers_canvas.call_tool(
            s.workspace,
            "canvas_delete_workspace",
            {"workspace_slug": "scratch"},
        )
        assert json.loads(body) == {"slug": "scratch", "deleted": True}
        assert await s.workspace.list_workspaces() == []

    asyncio.run(run())


def test_tool_definitions_include_align_and_distribute():
    names = {d["name"] for d in handlers_canvas.tool_definitions()}
    assert "canvas_align" in names
    assert "canvas_distribute" in names


def test_canvas_align_returns_moves():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a", x=0,  y=0,  width=100, height=100)
        await s.workspace.add_node("w1", id="b", x=50, y=30, width=100, height=100)
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_align",
            {"workspace_slug": "w1", "ids": ["a", "b"], "anchor": "top"},
        )
        out = json.loads(body)
        assert out["event_count"] == 1
        assert {m["id"] for m in out["moves"]} == {"b"}

    asyncio.run(run())


def test_canvas_distribute_returns_moves():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a", x=0,   y=0, width=100, height=100)
        await s.workspace.add_node("w1", id="b", x=120, y=0, width=100, height=100)
        await s.workspace.add_node("w1", id="c", x=300, y=0, width=100, height=100)
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_distribute",
            {"workspace_slug": "w1", "ids": ["a", "b", "c"], "axis": "horizontal"},
        )
        out = json.loads(body)
        assert out["event_count"] == 1
        assert {m["id"] for m in out["moves"]} == {"b"}

    asyncio.run(run())


def test_canvas_align_unknown_node_returns_error():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_align",
            {"workspace_slug": "w1", "ids": ["a", "ghost"], "anchor": "top"},
        )
        assert "error" in json.loads(body)

    asyncio.run(run())


def test_canvas_organize_subtree_returns_moves():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="r")
        await s.workspace.add_node("w1", id="a", x=-99, y=-99)
        await s.workspace.add_node("w1", id="b", x=99, y=99)
        await s.workspace.add_edge("w1", source="a", target="r")
        await s.workspace.add_edge("w1", source="b", target="r")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_organize_subtree",
            {"workspace_slug": "w1", "root_id": "r"},
        )
        out = json.loads(body)
        assert out["event_count"] == 2
        assert {m["id"] for m in out["moves"]} == {"a", "b"}

    asyncio.run(run())


def test_canvas_organize_subtree_inputschema_advertises_direction():
    # The MCP tool's inputSchema must surface the `direction` enum so agent
    # callers can discover it. Don't let the schema drift from the handler.
    defs = {d["name"]: d for d in handlers_canvas.tool_definitions()}
    schema = defs["canvas_organize_subtree"]["inputSchema"]
    direction = schema["properties"]["direction"]
    assert direction["enum"] == ["outgoing", "incoming", "any"]
    assert direction["default"] == "any"


def test_canvas_organize_subtree_direction_incoming_excludes_parent():
    """MCP-level parity test: organising from a mid-tree manager with
    direction='incoming' must NOT drag the CEO in."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="ceo")
        await s.workspace.add_node("w1", id="m1")
        await s.workspace.add_node("w1", id="r1", x=-99, y=-99)
        await s.workspace.add_node("w1", id="r2", x=99, y=99)
        await s.workspace.add_edge("w1", source="m1", target="ceo")
        await s.workspace.add_edge("w1", source="r1", target="m1")
        await s.workspace.add_edge("w1", source="r2", target="m1")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_organize_subtree",
            {"workspace_slug": "w1", "root_id": "m1", "direction": "incoming"},
        )
        out = json.loads(body)
        moved = {m["id"] for m in out["moves"]}
        assert moved == {"r1", "r2"}

    asyncio.run(run())


def test_canvas_organize_subtree_unknown_direction_returns_error():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="r")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_organize_subtree",
            {"workspace_slug": "w1", "root_id": "r", "direction": "sideways"},
        )
        assert "error" in json.loads(body)

    asyncio.run(run())


def test_canvas_create_sub_canvas_tool_is_registered():
    names = {d["name"] for d in handlers_canvas.tool_definitions()}
    assert "canvas_create_sub_canvas" in names


def test_canvas_create_sub_canvas_provisions_child_and_links():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("plant")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_create_sub_canvas",
            {
                "parent_slug": "plant",
                "slug": "pump-loop",
                "title": "Pump Loop",
                "x": 10,
                "y": 20,
            },
        )
        out = json.loads(body)
        assert out["child"]["slug"] == "pump-loop"
        assert out["node"]["node_type"] == "canvas"
        assert out["node"]["data"]["canvas_slug"] == "pump-loop"
        assert out["event"]["type"] == "NodeAdded"
        state = await s.workspace.get_state("plant")
        canvas_nodes = [n for n in state["nodes"] if n["node_type"] == "canvas"]
        assert len(canvas_nodes) == 1

    asyncio.run(run())


def test_canvas_create_sub_canvas_rejects_self_link():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("plant")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_create_sub_canvas",
            {"parent_slug": "plant", "slug": "plant"},
        )
        assert "error" in json.loads(body)

    asyncio.run(run())


def test_canvas_update_node_with_parent_dispatches_reparent():
    """`canvas_update_node {parent: <id>}` emits `NodeReparented`, mirroring HTTP."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="area", node_type="area")
        await s.workspace.add_node("w1", id="child", node_type="concept")
        body = await handlers_canvas.call_tool(
            s.workspace,
            "canvas_update_node",
            {"workspace_slug": "w1", "id": "child", "parent": "area"},
        )
        out = json.loads(body)
        assert out["event"]["type"] == "NodeReparented"
        assert out["event"]["payload"]["parent"] == "area"

    asyncio.run(run())


def test_canvas_list_placeholders_tool_is_registered():
    names = {d["name"] for d in handlers_canvas.tool_definitions()}
    assert "canvas_list_placeholders" in names


def test_canvas_list_placeholders_returns_flagged_nodes():
    """Only nodes with `data.placeholder == true` come back, with hint."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node(
            "w1", id="a", node_type="spec", label="Max pressure",
            data={"placeholder": True, "placeholder_hint": "Max inlet pressure"},
        )
        await s.workspace.add_node(
            "w1", id="b", node_type="spec", label="Filled",
            data={"rows": [{"key": "k", "value": "v"}]},
        )
        await s.workspace.add_node(
            "w1", id="c", node_type="concept", label="Empty box",
            data={"placeholder": True},
        )
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_list_placeholders",
            {"workspace_slug": "w1"},
        )
        items = json.loads(body)
        assert {it["id"] for it in items} == {"a", "c"}
        by_id = {it["id"]: it for it in items}
        assert by_id["a"]["hint"] == "Max inlet pressure"
        assert by_id["a"]["node_type"] == "spec"
        assert by_id["c"]["hint"] == ""
    asyncio.run(run())


def test_canvas_list_placeholders_empty_when_no_flags():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a", label="plain")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_list_placeholders",
            {"workspace_slug": "w1"},
        )
        assert json.loads(body) == []
    asyncio.run(run())


def test_canvas_update_node_clears_placeholder_round_trip():
    """Agent flow: list placeholders → update with real data + flag false."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node(
            "w1", id="a", node_type="spec", label="Temp range",
            data={"placeholder": True, "placeholder_hint": "Temperature range"},
        )
        # Agent finds the slot
        listing = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_list_placeholders",
            {"workspace_slug": "w1"},
        ))
        assert len(listing) == 1
        # Agent fills it in
        await handlers_canvas.call_tool(
            s.workspace, "canvas_update_node",
            {
                "workspace_slug": "w1", "id": "a",
                "data": {
                    "placeholder": False,
                    "placeholder_hint": "Temperature range",
                    "rows": [{"key": "min", "value": "-20°C"}],
                    "source_ref": {"page": 2, "bbox": [10, 20, 30, 40]},
                },
            },
        )
        listing2 = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_list_placeholders",
            {"workspace_slug": "w1"},
        ))
        assert listing2 == []
    asyncio.run(run())


def test_canvas_add_node_description_documents_structured_rows():
    """The add-node tool description must steer spec nodes toward `data.rows`
    (structured {key, value, source_ref}) over the prose `description` (#131)."""
    defs = {d["name"]: d for d in handlers_canvas.tool_definitions()}
    desc = defs["canvas_add_node"]["description"]
    assert "data.rows" in desc
    assert "key" in desc and "value" in desc and "source_ref" in desc
    # The structured-rows contract must lead; prose is the fallback.
    assert "description" in desc


def test_canvas_add_node_spec_description_only_returns_hint_but_succeeds():
    """A spec node created with prose `description` but no `rows` still writes,
    and the result carries a non-fatal `hint` nudging toward structured rows."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_node", {
            "workspace_slug": "w1", "id": "a", "node_type": "spec",
            "label": "Pumps",
            "data": {"description": "P-101 is 150mm, P-102 is 200mm"},
        })
        out = json.loads(body)
        # Non-fatal: the node was actually added.
        assert out["event"]["type"] == "NodeAdded"
        assert "error" not in out
        # ...and the hint steers toward rows.
        assert "hint" in out
        assert "data.rows" in out["hint"]

    asyncio.run(run())


def test_canvas_add_node_spec_with_rows_has_no_hint():
    """A spec node that already uses structured rows gets no nudge."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_node", {
            "workspace_slug": "w1", "id": "a", "node_type": "spec",
            "label": "Pumps",
            "data": {"rows": [{"key": "P-101", "value": "150 mm"}]},
        })
        out = json.loads(body)
        assert out["event"]["type"] == "NodeAdded"
        assert "hint" not in out

    asyncio.run(run())


def test_canvas_add_node_non_spec_with_description_has_no_hint():
    """The nudge is spec-specific: a fact/concept with a description is fine."""
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_node", {
            "workspace_slug": "w1", "id": "a", "node_type": "fact",
            "label": "Note", "data": {"description": "a free-form note"},
        })
        out = json.loads(body)
        assert out["event"]["type"] == "NodeAdded"
        assert "hint" not in out

    asyncio.run(run())


def test_canvas_update_node_rejects_self_parent():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a")
        body = await handlers_canvas.call_tool(
            s.workspace,
            "canvas_update_node",
            {"workspace_slug": "w1", "id": "a", "parent": "a"},
        )
        assert "error" in json.loads(body)

    asyncio.run(run())


# ── Node-write API hardening (#186/#189/#191/#192) ──────────────────────────

def test_canvas_add_node_accepts_type_alias():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_node", {
            "workspace_slug": "w1", "id": "a", "type": "fact", "x": 0, "y": 0,
        })
        out = json.loads(body)
        assert out["event"]["payload"]["node_type"] == "fact"

    asyncio.run(run())


def test_canvas_add_edge_accepts_type_alias():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="a", x=0, y=0)
        await s.workspace.add_node("w1", id="b", x=200, y=0)
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_edge", {
            "workspace_slug": "w1", "source": "a", "target": "b", "type": "anchored",
            "data": {"kind": "evidence", "source_ref": {"page": 1}},
        })
        out = json.loads(body)
        assert out["event"]["payload"]["edge_type"] == "anchored"

    asyncio.run(run())


def test_canvas_add_node_auto_places_and_returns_position():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        # No x/y -> auto-place; position is echoed back.
        b1 = json.loads(await handlers_canvas.call_tool(s.workspace, "canvas_add_node", {
            "workspace_slug": "w1", "node_type": "fact", "width": 120, "height": 80,
        }))
        assert b1["position"] == {"x": 0.0, "y": 0.0}
        b2 = json.loads(await handlers_canvas.call_tool(s.workspace, "canvas_add_node", {
            "workspace_slug": "w1", "node_type": "fact", "width": 120, "height": 80,
        }))
        assert b2["position"] != b1["position"]

    asyncio.run(run())


def test_canvas_add_node_warns_on_unrendered_data_key():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(s.workspace, "canvas_add_node", {
            "workspace_slug": "w1", "node_type": "fact", "x": 0, "y": 0,
            "data": {"body": "this never renders"},
        })
        out = json.loads(body)
        assert "warning" in out and "body" in out["warning"]


    asyncio.run(run())


def test_canvas_node_types_tool_returns_contract():
    async def run():
        s = make_in_memory_services()
        body = await handlers_canvas.call_tool(s.workspace, "canvas_node_types", {"node_type": "fact"})
        out = json.loads(body)
        assert out[0]["name"] == "fact"
        assert out[0]["body_field"] == "text"

    asyncio.run(run())


def test_canvas_update_node_data_merges_via_mcp():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node(
            "w1", id="a", node_type="fact", x=0, y=0,
            data={"text": "x", "source_ref": {"page": 1}},
        )
        body = await handlers_canvas.call_tool(s.workspace, "canvas_update_node", {
            "workspace_slug": "w1", "id": "a", "data": {"text": "y"},
        })
        out = json.loads(body)
        node = next(n for n in out["state"]["nodes"] if n["id"] == "a")
        assert node["data"]["text"] == "y"
        assert node["data"]["source_ref"] == {"page": 1}

    asyncio.run(run())


def test_canvas_reference_create_list_attach_roundtrip():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        await s.workspace.add_node("w1", id="n1", node_type="fact")
        created = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_create_reference",
            {
                "workspace_slug": "w1",
                "source_ref": {"slug": "d", "page": 2, "region_id": "r1"},
                "label": "Inlet",
            },
        ))
        ref = created["reference"]
        assert ref["id"]
        assert ref["created_by"] == "agent"  # MCP default
        listed = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_list_references", {"workspace_slug": "w1"},
        ))
        assert [r["id"] for r in listed] == [ref["id"]]
        attached = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_attach_reference",
            {"workspace_slug": "w1", "reference_id": ref["id"], "node_id": "n1"},
        ))
        assert attached["event"]["type"] == "ReferenceAttached"
        node = next(n for n in attached["state"]["nodes"] if n["id"] == "n1")
        assert node["data"]["reference_id"] == ref["id"]

    asyncio.run(run())


def test_canvas_reference_remove_and_update_roundtrip():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        created = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_create_reference",
            {"workspace_slug": "w1", "source_ref": {"slug": "d", "page": 1}, "label": "old"},
        ))
        ref = created["reference"]
        updated = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_update_reference",
            {"workspace_slug": "w1", "reference_id": ref["id"], "label": "new"},
        ))
        assert updated["event"]["type"] == "ReferenceUpdated"
        listed = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_list_references", {"workspace_slug": "w1"},
        ))
        assert listed[0]["label"] == "new"
        removed = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_remove_reference",
            {"workspace_slug": "w1", "reference_id": ref["id"]},
        ))
        assert removed["event"]["type"] == "ReferenceRemoved"
        listed2 = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_list_references", {"workspace_slug": "w1"},
        ))
        assert listed2 == []

    asyncio.run(run())


def test_canvas_remove_unknown_reference_returns_error():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        out = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_remove_reference",
            {"workspace_slug": "w1", "reference_id": "ghost"},
        ))
        assert "error" in out

    asyncio.run(run())


def test_canvas_create_reference_malformed_returns_error():
    async def run():
        s = make_in_memory_services()
        await s.workspace.create_workspace("w1")
        out = json.loads(await handlers_canvas.call_tool(
            s.workspace, "canvas_create_reference",
            {"workspace_slug": "w1", "source_ref": {"page": 1}},
        ))
        assert "error" in out

    asyncio.run(run())
