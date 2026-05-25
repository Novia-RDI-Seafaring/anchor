"""FmuService — orchestrates inspection and simulation.

Pure orchestrator over the FmuRuntime + FmuStore ports. No I/O imports.
Emits events on the canvas EventBus so any subscriber (browser, agent
harness, dashboard) sees simulation lifecycle live.
"""
from __future__ import annotations

import time
from typing import Any

from anchor.core.clock import Clock, SystemClock
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_event_id, slugify
from anchor.core.ports.event_bus import EventBus
from anchor.extensions.anchor_fmus.core.events import (
    FmuInspected,
    SimulationCompleted,
    SimulationFailed,
    SimulationStarted,
)
from anchor.extensions.anchor_fmus.core.ports import FmuRuntime, FmuStore
from anchor.extensions.anchor_fmus.core.schemas import (
    FmuModel,
    SimulationRun,
    TimeSeries,
)


class FmuService:
    def __init__(
        self,
        store: FmuStore,
        runtime: FmuRuntime,
        bus: EventBus,
        *,
        clock: Clock | None = None,
        global_workspace_id: str = "_global",
    ) -> None:
        self.store = store
        self.runtime = runtime
        self.bus = bus
        self.clock: Clock = clock or SystemClock()
        self._gid = global_workspace_id

    async def upload_and_inspect(self, fmu_bytes: bytes, filename: str) -> FmuModel:
        path = await self.store.stash_fmu(fmu_bytes, filename)
        model = await self.runtime.inspect(path)
        # Backfill slug from filename if the runtime didn't set one
        updates: dict[str, Any] = {}
        if not model.slug:
            updates["slug"] = slugify(filename.replace(".fmu", ""))
        # Stamp the runtime's synthetic provenance onto the saved model so
        # listings and node renderers can show a [SYNTHETIC] badge even
        # after a restart that re-reads from disk.
        updates["synthetic"] = bool(getattr(self.runtime, "synthetic", False))
        model = model.model_copy(update=updates)
        await self.store.write_model_summary(model.slug, model)
        await self._publish(FmuInspected(fmu_slug=model.slug, variable_count=len(model.variables)))
        return model

    async def list_models(self) -> list[FmuModel]:
        return await self.store.list_fmus()

    async def get_model(self, slug: str) -> FmuModel | None:
        return await self.store.get_model(slug)

    async def simulate(
        self,
        fmu_slug: str,
        *,
        parameter_overrides: dict[str, float] | None = None,
        stop_time: float = 1.0,
        output_interval: float = 0.01,
    ) -> SimulationRun:
        path = await self.store.get_fmu_path(fmu_slug)
        if path is None:
            raise FileNotFoundError(f"unknown FMU slug: {fmu_slug}")

        synthetic = bool(getattr(self.runtime, "synthetic", False))
        run = SimulationRun(
            fmu_slug=fmu_slug,
            started_at=self.clock.now(),
            stop_time=stop_time,
            output_interval=output_interval,
            parameter_overrides=parameter_overrides or {},
            synthetic=synthetic,
        )
        await self._publish(SimulationStarted(
            simulation_id=run.id, fmu_slug=fmu_slug,
            parameter_overrides=run.parameter_overrides,
        ))
        try:
            t0 = time.monotonic()
            series = await self.runtime.simulate(path, run=run)
            # Carry the synthetic provenance onto the series too — clients
            # that pull just the time-series (e.g. the plot node) shouldn't
            # have to fetch the run separately to know it's demo data.
            if synthetic and not series.synthetic:
                series = series.model_copy(update={"synthetic": True})
            run = run.model_copy(update={
                "status": "completed",
                "completed_at": self.clock.now(),
            })
            duration_ms = int((time.monotonic() - t0) * 1000)
            await self.store.write_simulation(run, series)
            await self._publish(SimulationCompleted(
                simulation_id=run.id, fmu_slug=fmu_slug, duration_ms=duration_ms,
                summary={"points": len(series.time), "variables": len(series.variables)},
            ))
            return run
        except Exception as exc:
            run = run.model_copy(update={
                "status": "failed", "error": str(exc),
                "completed_at": self.clock.now(),
            })
            await self._publish(SimulationFailed(
                simulation_id=run.id, fmu_slug=fmu_slug, error=str(exc),
            ))
            raise

    async def get_series(self, simulation_id: str) -> TimeSeries | None:
        return await self.store.get_series(simulation_id)

    async def list_simulations(self, fmu_slug: str | None = None) -> list[SimulationRun]:
        return await self.store.list_simulations(fmu_slug=fmu_slug)

    async def _publish(self, evt: Any) -> None:
        await self.bus.publish(DomainEvent(
            id=new_event_id(),
            ts=self.clock.now(),
            workspace_id=self._gid,
            type=evt.type,
            payload=evt.model_dump(),
        ))
