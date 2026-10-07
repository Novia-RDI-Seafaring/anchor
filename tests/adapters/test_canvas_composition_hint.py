"""A large proposal set that groups nothing gets a nudge.

The mirror of the spec-rows hint: that one steers values into rows, this one
steers an answer into a shape a human can read. Non-blocking either way -- a
flat set is still a valid set.
"""
from __future__ import annotations

import json

from anchor.adapters.mcp.handlers_canvas import (
    _COMPOSITION_HINT_MIN_MEMBERS,
    _composition_hint,
)


def _members(n: int, start: int = 0) -> list[dict[str, str]]:
    return [{"id": f"n{i}"} for i in range(start, start + n)]


def _state(nodes: list[dict[str, object]]) -> dict[str, object]:
    return {"nodes": nodes}


def _plain(ids: list[str]) -> list[dict[str, object]]:
    return [{"id": i, "node_type": "fact"} for i in ids]


def test_big_ungrouped_set_is_nudged():
    members = _members(_COMPOSITION_HINT_MIN_MEMBERS)
    hint = _composition_hint(
        {"members": members}, _state(_plain([m["id"] for m in members]))
    )
    assert hint is not None
    assert "`area`" in hint
    assert str(_COMPOSITION_HINT_MIN_MEMBERS) in hint


def test_a_set_containing_an_area_is_left_alone():
    members = _members(_COMPOSITION_HINT_MIN_MEMBERS + 4)
    nodes = _plain([m["id"] for m in members])
    nodes[2]["node_type"] = "area"
    assert _composition_hint({"members": members}, _state(nodes)) is None


def test_a_small_set_is_left_alone():
    members = _members(_COMPOSITION_HINT_MIN_MEMBERS - 1)
    hint = _composition_hint(
        {"members": members}, _state(_plain([m["id"] for m in members]))
    )
    assert hint is None


def test_an_area_outside_the_set_does_not_count():
    # Grouping has to be part of what was proposed; an area someone else
    # drew earlier says nothing about this batch.
    members = _members(_COMPOSITION_HINT_MIN_MEMBERS)
    nodes = _plain([m["id"] for m in members])
    nodes.append({"id": "other", "node_type": "area"})
    assert _composition_hint({"members": members}, _state(nodes)) is not None


def test_members_may_be_bare_ids():
    members = [f"n{i}" for i in range(_COMPOSITION_HINT_MIN_MEMBERS)]
    nodes = _plain(members)
    nodes[0]["node_type"] = "area"
    assert _composition_hint({"members": members}, _state(nodes)) is None


def test_nodes_as_a_mapping_are_handled():
    members = _members(_COMPOSITION_HINT_MIN_MEMBERS)
    nodes = {m["id"]: {"id": m["id"], "node_type": "fact"} for m in members}
    assert _composition_hint({"members": members}, {"nodes": nodes}) is not None
    nodes["n0"]["node_type"] = "area"
    assert _composition_hint({"members": members}, {"nodes": nodes}) is None


def test_malformed_input_is_silent():
    assert _composition_hint(None, {"nodes": []}) is None
    assert _composition_hint({"members": "nope"}, {"nodes": []}) is None
    assert _composition_hint({"members": _members(20)}, None) is None
    assert _composition_hint({}, {}) is None


def test_hint_rides_the_propose_set_result():
    import asyncio

    from anchor.adapters.mcp.handlers_canvas import call_tool
    from tests.fixtures.services import make_in_memory_services

    services = make_in_memory_services()
    svc = services.workspace

    async def run():
        await svc.create_workspace("board", title="board")
        ids = []
        for i in range(_COMPOSITION_HINT_MIN_MEMBERS):
            _ws, event = await svc.add_node(
                "board", node_type="fact", label=f"f{i}", x=0, y=i * 10,
            )
            ids.append(event.payload["id"])
        return json.loads(
            await call_tool(
                svc,
                "canvas_propose_set",
                {"workspace_slug": "board", "reason": "findings", "members": ids},
            )
        )

    out = asyncio.run(run())
    assert "proposal_set" in out
    assert "`area`" in out["hint"]
