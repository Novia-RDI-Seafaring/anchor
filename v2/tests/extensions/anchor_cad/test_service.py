"""Tests for CadService — ingestion, listing, parameter updates, event flow."""
from __future__ import annotations

import asyncio

import pytest

from anchor.extensions.anchor_cad.core.schemas import (
    CadGeometryStats,
    CadModel,
    CadParameter,
)
from anchor.extensions.anchor_cad.core.services import CadService
from anchor.extensions.anchor_cad.infra.memory_store import MemoryCadStore
from anchor.infra.bus.memory_bus import MemoryEventBus


class FakeInspector:
    """Returns a fixed CadModel so tests don't depend on real geometry parsing."""

    def __init__(self, model: CadModel) -> None:
        self.model = model

    async def inspect(self, cad_path, *, kind=None):  # noqa: ARG002
        return self.model.model_copy(update={"kind": kind or self.model.kind})


def _make_service(model: CadModel) -> tuple[CadService, MemoryEventBus]:
    bus = MemoryEventBus()
    return CadService(MemoryCadStore(), FakeInspector(model), bus), bus


def test_upload_and_inspect_persists_model_and_emits_event():
    sample = CadModel(
        slug="impeller",
        filename="impeller.stl",
        kind="stl",
        parameters=[CadParameter(name="diameter", value=320)],
        geometry=CadGeometryStats(triangle_count=18412),
    )
    svc, bus = _make_service(sample)

    async def run():
        events: list = []
        sub_task = asyncio.create_task(_collect(bus, events, expected=1))
        await asyncio.sleep(0)  # let the subscriber attach

        result = await svc.upload_and_inspect(b"fake-bytes", "impeller.stl")

        await asyncio.wait_for(sub_task, timeout=1.0)
        return result, events

    result, events = asyncio.run(run())
    assert result.slug == "impeller"
    assert result.kind == "stl"
    assert result.geometry.triangle_count == 18412
    assert events[0].type == "CadIngested"
    assert events[0].payload["cad_slug"] == "impeller"
    assert events[0].payload["parameter_count"] == 1


def test_list_models_returns_what_was_ingested():
    sample = CadModel(slug="part-a", filename="part-a.obj", kind="obj")
    svc, _ = _make_service(sample)

    async def run():
        await svc.upload_and_inspect(b"x", "part-a.obj")
        return await svc.list_models()

    models = asyncio.run(run())
    assert len(models) == 1
    assert models[0].slug == "part-a"


def test_set_parameter_updates_value_and_emits_change_event():
    sample = CadModel(
        slug="cup",
        filename="cup.scad",
        kind="openscad",
        parameters=[
            CadParameter(name="height", value=80),
            CadParameter(name="wall", value=2),
        ],
    )
    svc, bus = _make_service(sample)

    async def run():
        events: list = []
        await svc.upload_and_inspect(b"x", "cup.scad")
        sub_task = asyncio.create_task(_collect(bus, events, expected=1))
        await asyncio.sleep(0)
        updated = await svc.set_parameter("cup", "height", 120)
        await asyncio.wait_for(sub_task, timeout=1.0)
        return updated, events

    updated, events = asyncio.run(run())
    height_param = next(p for p in updated.parameters if p.name == "height")
    assert height_param.value == 120
    assert events[0].type == "CadParameterChanged"
    assert events[0].payload["new_value"] == 120
    assert events[0].payload["old_value"] == 80


def test_set_parameter_unknown_slug_raises():
    sample = CadModel(slug="x", filename="x.stl", kind="stl")
    svc, _ = _make_service(sample)

    async def run():
        with pytest.raises(FileNotFoundError):
            await svc.set_parameter("does-not-exist", "p", 1)

    asyncio.run(run())


def test_kind_inferred_from_filename_when_inspector_returns_unknown():
    sample = CadModel(slug="m", filename="m", kind="unknown")
    svc, _ = _make_service(sample)

    async def run():
        return await svc.upload_and_inspect(b"x", "model.stp")

    result = asyncio.run(run())
    assert result.kind == "step"


async def _collect(bus: MemoryEventBus, sink: list, *, expected: int) -> None:
    async for evt in bus.subscribe():
        sink.append(evt)
        if len(sink) >= expected:
            return
