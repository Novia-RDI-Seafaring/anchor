"""A spec value written with no source comes back named, with how to cite it."""
from __future__ import annotations

import asyncio
import json

from anchor.adapters.mcp.handlers_canvas import _unsourced, call_tool
from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore


class _Node:
    def __init__(self, data):
        self.data = data


def test_only_rows_with_a_value_and_no_source_are_named():
    node = _Node({"rows": [
        {"key": "Max flow", "value": "12 m3/h", "source_ref": {"slug": "px", "page": 1}},
        {"key": "Temperature", "value": "-10 to +140"},
        {"key": "Height", "value": ""},
    ]})
    out = _unsourced(node)
    assert out["rows"] == ["Temperature"]
    assert "cell" in out["next"]
    assert _unsourced(_Node({"rows": [{"key": "Height", "value": ""}]})) is None


def test_add_and_update_report_unsourced_rows():
    async def run():
        svc = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
        await svc.create_workspace("w")
        added = json.loads(await call_tool(svc, "canvas_add_node", {
            "workspace_slug": "w", "node_type": "spec", "label": "PX-5",
            "data": {"rows": [{"key": "Max inlet pressure", "value": "6 bar"}]},
        }))
        assert added["unsourced"]["rows"] == ["Max inlet pressure"]
        updated = json.loads(await call_tool(svc, "canvas_update_node", {
            "workspace_slug": "w", "id": added["node_id"],
            "data": {"rows": [{"key": "Max inlet pressure", "value": "6 bar",
                               "source_ref": {"slug": "px", "page": 2}}]},
        }))
        assert "unsourced" not in updated

    asyncio.run(run())


def test_quotes_that_could_not_be_placed_come_back_with_how_to_fix_them():
    from anchor.adapters.mcp.handlers_canvas import _quote_problems

    node = _Node({"rows": [{"key": "Temperature", "value": "+140 °C", "source_ref": {
        "slug": "px", "page": 2, "quotes": [
            {"exact": "EPDM", "problem": "ambiguous", "candidates": ["a EPDM b", "c EPDM d"]},
            {"exact": "+140", "boxes": [[1, 2, 3, 4]]},
        ]}}]})
    out = _quote_problems(node)
    assert [p["exact"] for p in out["problems"]] == ["EPDM"]
    assert out["problems"][0]["row"] == "Temperature"
    assert "prefix" in out["next"]
