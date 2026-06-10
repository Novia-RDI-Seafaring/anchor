"""End-to-end service tests using the in-memory workspace store."""
from __future__ import annotations

import asyncio
from pathlib import Path

from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_sysml import mcp_handlers
from anchor.extensions.anchor_sysml.core.services import SysmlService
from anchor.extensions.anchor_sysml.infra.canvas_mapper import SysmlCanvasMapper
from anchor.extensions.anchor_sysml.infra.parser import SysmlTextParser
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore


FIXTURES = Path(__file__).parent / "fixtures"


def _make_service():
    bus = MemoryEventBus()
    store = MemoryWorkspaceStore()
    workspace = WorkspaceService(store, bus)
    svc = SysmlService(
        workspace=workspace,
        bus=bus,
        parser=SysmlTextParser(),
        mapper=SysmlCanvasMapper(),
    )
    return svc, workspace


def test_render_lkh_pump_fixture_creates_expected_nodes_and_edges():
    svc, workspace = _make_service()

    async def run():
        await workspace.create_workspace("lkh", title="LKH demo")
        text = (FIXTURES / "lkh_pump.sysml").read_text()
        result = await svc.render(
            workspace_slug="lkh", text=text, filename="lkh_pump.sysml",
        )
        state = await workspace.get_state("lkh")
        return result, state

    result, state = asyncio.run(run())

    nodes = state["nodes"]
    edges = state["edges"]
    types = {n["node_type"] for n in nodes}
    assert "sysml:package" in types
    assert "sysml:block" in types
    assert "sysml:requirement" in types

    # PumpEquipment package + Pump + LKH5 + LKH10 + LKH70 + FluidPort + MaxPressure (req)
    block_labels = {n["label"] for n in nodes if n["node_type"] == "sysml:block"}
    assert {"Pump", "LKH5", "LKH10", "LKH70", "FluidPort"} <= block_labels

    req_labels = {n["label"] for n in nodes if n["node_type"] == "sysml:requirement"}
    assert "MaxPressure" in req_labels

    inheritance = [e for e in edges if e["data"].get("marker") == "inheritance"]
    assert len(inheritance) == 3  # LKH5/LKH10/LKH70 → Pump

    # Pump block carries the metadata pass-through (ISO 15926 URI).
    pump_node = next(n for n in nodes if n["label"] == "Pump")
    assert pump_node["data"]["metadata"].get("@iso15926-uri")

    # Render result mirrors what the service stored.
    assert len(result.node_ids) == len(nodes)
    assert len(result.edge_ids) == len(inheritance) + sum(
        1 for e in edges if e["data"].get("marker") in {"satisfy", "subject", "association", "interface-connection"}
    )


def test_render_emits_sysml_rendered_event():
    svc, workspace = _make_service()

    async def run():
        await workspace.create_workspace("ev", title="ev")
        events: list = []

        async def collect():
            async for evt in svc.bus.subscribe("ev"):
                events.append(evt)
                if any(e.type == "SysmlRendered" for e in events):
                    return

        sub = asyncio.create_task(collect())
        await asyncio.sleep(0)
        await svc.render(workspace_slug="ev", text="package T {}", filename="t.sysml")
        await asyncio.wait_for(sub, timeout=1.0)
        return events

    events = asyncio.run(run())
    assert any(e.type == "SysmlRendered" for e in events)


def test_export_returns_phase1_stub_text():
    svc, workspace = _make_service()

    async def run():
        await workspace.create_workspace("x", title="x")
        return await svc.export(workspace_slug="x")

    text = asyncio.run(run())
    assert "Phase 1 stub" in text
    assert "TODO" in text


def test_mcp_tool_definitions_use_safe_names():
    defs = mcp_handlers.tool_definitions()
    names = {d["name"] for d in defs}
    assert {"sysml_render", "sysml_export"} <= names
    assert all("." not in name for name in names)
    assert all(name.startswith("sysml_") for name in names)


def test_mcp_accepts_legacy_dotted_names():
    svc, workspace = _make_service()

    async def run():
        await workspace.create_workspace("legacy", title="legacy")
        body = await mcp_handlers.call_tool(
            svc,
            "sysml.render",
            {"workspace_slug": "legacy", "text": "package T {}"},
        )
        assert "node_ids" in body

    asyncio.run(run())


def test_render_drone_fixture_end_to_end():
    svc, workspace = _make_service()

    async def run():
        await workspace.create_workspace("drone")
        text = (FIXTURES / "drone_base_architecture.sysml").read_text()
        result = await svc.render(
            workspace_slug="drone", text=text, filename="drone.sysml",
        )
        state = await workspace.get_state("drone")
        return result, state

    result, state = asyncio.run(run())
    nodes = state["nodes"]
    # Four packages + drone block + requirements (longDistance, totalMass, battery, maxCapacity)
    pkg_count = sum(1 for n in nodes if n["node_type"] == "sysml:package")
    req_count = sum(1 for n in nodes if n["node_type"] == "sysml:requirement")
    assert pkg_count == 4
    assert req_count == 4
    # diagnostics surface for `#derivation connection {…}` and any state/action
    assert all(d.level in {"info", "warning", "error"} for d in result.diagnostics)
