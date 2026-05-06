"""Ports for the FMU extension — protocols implemented by infra."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from anchor.extensions.anchor_fmus.core.schemas import (
    FmuModel,
    SimulationRun,
    TimeSeries,
)


class FmuRuntime(Protocol):
    """Inspect + simulate FMUs. Real impl: FMPy. Test impl: in-memory fake."""

    async def inspect(self, fmu_path: Path) -> FmuModel: ...

    async def simulate(
        self,
        fmu_path: Path,
        *,
        run: SimulationRun,
        on_progress: object | None = None,
    ) -> TimeSeries: ...


class FmuStore(Protocol):
    """Persist FMU bronze (raw .fmu files) + simulation runs + time series."""

    async def stash_fmu(self, fmu_bytes: bytes, filename: str) -> Path: ...

    async def get_fmu_path(self, slug: str) -> Path | None: ...

    async def list_fmus(self) -> list[FmuModel]: ...

    async def write_model_summary(self, slug: str, model: FmuModel) -> Path: ...

    async def get_model(self, slug: str) -> FmuModel | None: ...

    async def write_simulation(self, run: SimulationRun, series: TimeSeries) -> Path: ...

    async def list_simulations(self, fmu_slug: str | None = None) -> list[SimulationRun]: ...

    async def get_series(self, simulation_id: str) -> TimeSeries | None: ...
