"""Tests for the anchor_fmus extension — service, store, runtime, MCP tools."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from anchor.core.clock import FixedClock
from anchor.extensions.anchor_fmus import extension as fmu_ext
from anchor.extensions.anchor_fmus import mcp_handlers
from anchor.extensions.anchor_fmus.core.services import FmuService
from anchor.extensions.anchor_fmus.infra.fake_runtime import FakeFmuRuntime
from anchor.extensions.anchor_fmus.infra.fs_store import FsFmuStore
from anchor.extensions.anchor_fmus.infra.memory_store import MemoryFmuStore
from anchor.infra.bus.memory_bus import MemoryEventBus


def _service(store, runtime=None) -> FmuService:
    return FmuService(
        store=store,
        runtime=runtime or FakeFmuRuntime(),
        bus=MemoryEventBus(),
        clock=FixedClock(ts=1700000000.0),
    )


# ── extension manifest ──────────────────────────────────────────────────


def test_manifest_is_oip_compliant():
    m = fmu_ext.manifest(data_dir=Path("/tmp/x"))
    assert m["oip_version"] == "0.1"
    assert m["producer"]["name"] == "anchor-fmus"
    assert "application/x-fmu" in m["produces"]["source_kinds"]
    assert "fmu-variable" in m["produces"]["source_ref_kinds"]
    assert m["invocation"]["tools_namespace"] == "fmu"


def test_manifest_includes_ui_hints():
    m = fmu_ext.manifest()
    assert "node_types" in m["ui_hints"]
    types = {nt["name"] for nt in m["ui_hints"]["node_types"]}
    assert {"fmu:model", "fmu:variable", "fmu:plot"} == types


# ── service: inspect + simulate ────────────────────────────────────────


def test_inspect_persists_model():
    async def run():
        svc = _service(MemoryFmuStore())
        model = await svc.upload_and_inspect(b"FAKE-FMU-BYTES", "pump.fmu")
        assert model.slug == "pump"
        assert model.filename == "pump.fmu"
        # Round-trip through the store
        stored = await svc.get_model("pump")
        assert stored is not None
        assert {v.name for v in stored.variables} >= {"temp_in", "temp_out"}

    asyncio.run(run())


def test_simulate_produces_time_series():
    async def run():
        svc = _service(MemoryFmuStore())
        await svc.upload_and_inspect(b"x", "pump.fmu")
        run_meta = await svc.simulate("pump", stop_time=1.0, output_interval=0.1)
        assert run_meta.status == "completed"
        series = await svc.get_series(run_meta.id)
        assert series is not None
        assert len(series.time) >= 10
        assert "temp_out" in series.variables

    asyncio.run(run())


def test_simulate_unknown_fmu_raises():
    async def run():
        svc = _service(MemoryFmuStore())
        with pytest.raises(FileNotFoundError):
            await svc.simulate("does-not-exist")

    asyncio.run(run())


def test_simulate_emits_lifecycle_events():
    async def run():
        bus = MemoryEventBus()
        svc = FmuService(MemoryFmuStore(), FakeFmuRuntime(), bus, clock=FixedClock(ts=1.0))
        seen: list[str] = []

        async def subscribe():
            async for evt in bus.subscribe(None):
                seen.append(evt.type)
                if "SimulationCompleted" in seen:
                    return

        sub = asyncio.create_task(subscribe())
        await asyncio.sleep(0)
        await svc.upload_and_inspect(b"x", "pump.fmu")
        await svc.simulate("pump", stop_time=0.1, output_interval=0.05)
        await asyncio.wait_for(sub, timeout=2.0)
        assert "FmuInspected" in seen
        assert "SimulationStarted" in seen
        assert "SimulationCompleted" in seen

    asyncio.run(run())


def test_list_simulations_filters_by_slug():
    async def run():
        svc = _service(MemoryFmuStore())
        await svc.upload_and_inspect(b"x", "pump.fmu")
        await svc.upload_and_inspect(b"y", "valve.fmu")
        await svc.simulate("pump", stop_time=0.1, output_interval=0.05)
        await svc.simulate("valve", stop_time=0.1, output_interval=0.05)
        pump_runs = await svc.list_simulations("pump")
        valve_runs = await svc.list_simulations("valve")
        assert len(pump_runs) == 1 and pump_runs[0].fmu_slug == "pump"
        assert len(valve_runs) == 1 and valve_runs[0].fmu_slug == "valve"

    asyncio.run(run())


# ── FsFmuStore ──────────────────────────────────────────────────────────


def test_fs_store_round_trip(tmp_path):
    async def run():
        store = FsFmuStore(tmp_path)
        svc = _service(store)
        await svc.upload_and_inspect(b"FAKE-FMU", "pump.fmu")
        # FS layout
        assert (tmp_path / "fmus" / "bronze" / "pump.fmu").exists()
        assert (tmp_path / "fmus" / "models" / "pump.json").exists()
        # Round-trip
        run_meta = await svc.simulate("pump", stop_time=0.2, output_interval=0.1)
        assert (tmp_path / "fmus" / "simulations" / run_meta.id / "run.json").exists()
        assert (tmp_path / "fmus" / "simulations" / run_meta.id / "series.json").exists()
        # Re-instantiate to verify load-from-disk
        store2 = FsFmuStore(tmp_path)
        svc2 = _service(store2)
        models = await svc2.list_models()
        assert {m.slug for m in models} == {"pump"}
        runs = await svc2.list_simulations()
        assert len(runs) == 1

    asyncio.run(run())


# ── MCP handlers ────────────────────────────────────────────────────────


def test_mcp_inspect_tool(tmp_path):
    async def run():
        # Write a fake FMU file (FakeFmuRuntime ignores the contents)
        fake = tmp_path / "fake.fmu"
        fake.write_bytes(b"FAKE")
        svc = _service(MemoryFmuStore())
        body = await mcp_handlers.call_tool(svc, "fmu.inspect", {"fmu_path": str(fake)})
        out = json.loads(body)
        assert out["slug"] == "fake"
        assert any(v["name"] == "temp_out" for v in out["variables"])

    asyncio.run(run())


def test_mcp_simulate_then_get_results(tmp_path):
    async def run():
        fake = tmp_path / "p.fmu"
        fake.write_bytes(b"FAKE")
        svc = _service(MemoryFmuStore())
        await mcp_handlers.call_tool(svc, "fmu.inspect", {"fmu_path": str(fake)})
        sim_body = await mcp_handlers.call_tool(svc, "fmu.simulate", {
            "slug": "p", "stop_time": 0.5, "output_interval": 0.1,
        })
        sim_id = json.loads(sim_body)["id"]
        results_body = await mcp_handlers.call_tool(svc, "fmu.get_results", {
            "simulation_id": sim_id,
        })
        results = json.loads(results_body)
        assert "time" in results and "variables" in results

    asyncio.run(run())


def test_mcp_unknown_tool_returns_json_error():
    async def run():
        svc = _service(MemoryFmuStore())
        body = await mcp_handlers.call_tool(svc, "fmu.nope", {})
        assert "error" in json.loads(body)

    asyncio.run(run())


def test_mcp_list_models_includes_inspected(tmp_path):
    async def run():
        fake = tmp_path / "x.fmu"
        fake.write_bytes(b"FAKE")
        svc = _service(MemoryFmuStore())
        await mcp_handlers.call_tool(svc, "fmu.inspect", {"fmu_path": str(fake)})
        body = await mcp_handlers.call_tool(svc, "fmu.list_models", {})
        models = json.loads(body)
        assert any(m["slug"] == "x" for m in models)

    asyncio.run(run())


def test_mcp_tool_definitions_have_required_fields():
    defs = mcp_handlers.tool_definitions()
    assert all("name" in d and "description" in d and "inputSchema" in d for d in defs)
    names = {d["name"] for d in defs}
    assert {"fmu.inspect", "fmu.simulate", "fmu.list_models"} <= names
    # Every name is namespaced under "fmu."
    assert all(name.startswith("fmu.") for name in names)
