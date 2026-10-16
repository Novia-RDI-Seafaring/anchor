"""A spec row's name is its ``key``; other name fields are moved there."""
from __future__ import annotations

from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore


async def test_rows_named_by_label_or_name_are_named_by_key():
    ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
    await ws.create_workspace("g")
    state, _ = await ws.add_node("g", id="s", node_type="spec", data={"rows": [
        {"label": "Min temp", "value": "-10 °C"},
        {"name": "Max temp", "value": "140 °C"},
        {"key": "Speed", "label": "ignored", "value": "2900 rpm"},
    ]})
    rows = state.nodes["s"].data["rows"]
    assert [r["key"] for r in rows] == ["Min temp", "Max temp", "Speed"]
    assert "label" not in rows[0] and "name" not in rows[1]
    assert rows[2]["label"] == "ignored"


async def test_an_update_with_label_rows_is_named_too():
    ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
    await ws.create_workspace("g")
    await ws.add_node("g", id="s", node_type="spec", data={"rows": []})
    state, _ = await ws.update_node("g", "s", {"data": {"rows": [{"label": "Mass", "value": "29 kg"}]}})
    assert state.nodes["s"].data["rows"][0]["key"] == "Mass"
