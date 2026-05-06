"""CadService — orchestrates CAD inspection and (eventually) parameter tweaks.

Pure orchestrator over CadInspector + CadStore ports. Mirrors FmuService.
"""
from __future__ import annotations

from typing import Any

from anchor.core.clock import Clock, SystemClock
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_event_id, slugify
from anchor.core.ports.event_bus import EventBus
from anchor.extensions.anchor_cad.core.events import (
    CadIngestFailed,
    CadIngested,
    CadParameterChanged,
)
from anchor.extensions.anchor_cad.core.ports import CadInspector, CadStore
from anchor.extensions.anchor_cad.core.schemas import CadModel


_KIND_FROM_EXT: dict[str, str] = {
    ".stl": "stl",
    ".obj": "obj",
    ".step": "step",
    ".stp": "step",
    ".iges": "iges",
    ".igs": "iges",
    ".gltf": "gltf",
    ".glb": "gltf",
    ".jscad": "jscad",
    ".scad": "openscad",
}


def _kind_from_filename(filename: str) -> str:
    lower = filename.lower()
    for ext, kind in _KIND_FROM_EXT.items():
        if lower.endswith(ext):
            return kind
    return "unknown"


class CadService:
    def __init__(
        self,
        store: CadStore,
        inspector: CadInspector,
        bus: EventBus,
        *,
        clock: Clock | None = None,
        global_workspace_id: str = "_global",
    ) -> None:
        self.store = store
        self.inspector = inspector
        self.bus = bus
        self.clock: Clock = clock or SystemClock()
        self._gid = global_workspace_id

    async def upload_and_inspect(self, cad_bytes: bytes, filename: str) -> CadModel:
        try:
            path = await self.store.stash_cad(cad_bytes, filename)
            kind = _kind_from_filename(filename)
            model = await self.inspector.inspect(path, kind=kind)
            if not model.slug:
                stem = filename.rsplit(".", 1)[0]
                model = model.model_copy(update={"slug": slugify(stem)})
            if not model.kind or model.kind == "unknown":
                model = model.model_copy(update={"kind": kind})  # type: ignore[arg-type]
            if not model.filename:
                model = model.model_copy(update={"filename": filename})
            await self.store.write_model_summary(model.slug, model)
            await self._publish(CadIngested(
                cad_slug=model.slug,
                kind=model.kind,
                parameter_count=len(model.parameters),
                part_count=len(model.parts),
            ))
            return model
        except Exception as exc:  # surface the failure; don't swallow
            await self._publish(CadIngestFailed(filename=filename, error=str(exc)))
            raise

    async def list_models(self) -> list[CadModel]:
        return await self.store.list_cads()

    async def get_model(self, slug: str) -> CadModel | None:
        return await self.store.get_model(slug)

    async def set_parameter(
        self,
        cad_slug: str,
        parameter_name: str,
        value: float | int | str | bool,
    ) -> CadModel:
        """Tweak a parameter on a parametric model.

        Today this just updates the stored summary and emits an event; a
        future runtime would re-evaluate the parametric model and produce
        new geometry. The event-on-bus is the contract that lets a 3D
        viewport listen and re-render.
        """
        model = await self.store.get_model(cad_slug)
        if model is None:
            raise FileNotFoundError(f"unknown CAD slug: {cad_slug}")
        old_value: Any = None
        new_params = []
        for p in model.parameters:
            if p.name == parameter_name:
                old_value = p.value
                new_params.append(p.model_copy(update={"value": value}))
            else:
                new_params.append(p)
        updated = model.model_copy(update={"parameters": new_params})
        await self.store.write_model_summary(cad_slug, updated)
        await self._publish(CadParameterChanged(
            cad_slug=cad_slug, parameter_name=parameter_name,
            old_value=old_value, new_value=value,
        ))
        return updated

    async def _publish(self, evt: Any) -> None:
        await self.bus.publish(DomainEvent(
            id=new_event_id(),
            ts=self.clock.now(),
            workspace_id=self._gid,
            type=evt.type,
            payload=evt.model_dump(),
        ))
