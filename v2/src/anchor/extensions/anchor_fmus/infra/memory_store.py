"""In-memory FmuStore — used by tests and ephemeral mode."""
from __future__ import annotations

import asyncio
from pathlib import Path

from anchor.extensions.anchor_fmus.core.ports import FmuStore
from anchor.extensions.anchor_fmus.core.schemas import (
    FmuModel,
    SimulationRun,
    TimeSeries,
)


class MemoryFmuStore(FmuStore):
    def __init__(self) -> None:
        self._fmu_paths: dict[str, Path] = {}
        self._fmu_bytes: dict[str, bytes] = {}
        self._models: dict[str, FmuModel] = {}
        self._simulations: dict[str, SimulationRun] = {}
        self._series: dict[str, TimeSeries] = {}
        self._lock = asyncio.Lock()

    async def stash_fmu(self, fmu_bytes: bytes, filename: str) -> Path:
        async with self._lock:
            self._fmu_bytes[filename] = fmu_bytes
        path = Path(f"memory://fmus/{filename}")
        from anchor.core.ids import slugify
        slug = slugify(filename.replace(".fmu", ""))
        self._fmu_paths[slug] = path
        return path

    async def get_fmu_path(self, slug: str) -> Path | None:
        return self._fmu_paths.get(slug)

    async def list_fmus(self) -> list[FmuModel]:
        return list(self._models.values())

    async def write_model_summary(self, slug: str, model: FmuModel) -> Path:
        async with self._lock:
            self._models[slug] = model
        return Path(f"memory://fmus/{slug}/model.json")

    async def get_model(self, slug: str) -> FmuModel | None:
        return self._models.get(slug)

    async def write_simulation(self, run: SimulationRun, series: TimeSeries) -> Path:
        async with self._lock:
            self._simulations[run.id] = run
            self._series[run.id] = series
        return Path(f"memory://simulations/{run.id}.json")

    async def list_simulations(self, fmu_slug: str | None = None) -> list[SimulationRun]:
        runs = list(self._simulations.values())
        if fmu_slug is not None:
            runs = [r for r in runs if r.fmu_slug == fmu_slug]
        return runs

    async def get_series(self, simulation_id: str) -> TimeSeries | None:
        return self._series.get(simulation_id)
