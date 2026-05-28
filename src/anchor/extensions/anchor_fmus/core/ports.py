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
    """Inspect + simulate FMUs. Real impl: FMPy. Test impl: in-memory fake.

    ``synthetic`` lets the orchestrating service stamp every result it
    produces with provenance: ``True`` means "this came from a
    sinusoid-generator, not a real FMU solve", and HTTP/MCP/CLI surfaces
    expose that to the user/agent so they can't mistake demo output for a
    real engineering computation.
    """

    synthetic: bool

    async def inspect(self, fmu_path: Path) -> FmuModel:
        raise NotImplementedError

    async def simulate(
        self,
        fmu_path: Path,
        *,
        run: SimulationRun,
        on_progress: object | None = None,
    ) -> TimeSeries:
        raise NotImplementedError


class FmuStore(Protocol):
    """Persist FMU bronze (raw .fmu files) + simulation runs + time series."""

    async def stash_fmu(self, fmu_bytes: bytes, filename: str) -> Path:
        raise NotImplementedError

    async def get_fmu_path(self, slug: str) -> Path | None:
        raise NotImplementedError

    async def list_fmus(self) -> list[FmuModel]:
        raise NotImplementedError

    async def write_model_summary(self, slug: str, model: FmuModel) -> Path:
        raise NotImplementedError

    async def get_model(self, slug: str) -> FmuModel | None:
        raise NotImplementedError

    async def write_simulation(self, run: SimulationRun, series: TimeSeries) -> Path:
        raise NotImplementedError

    async def list_simulations(self, fmu_slug: str | None = None) -> list[SimulationRun]:
        raise NotImplementedError

    async def get_series(self, simulation_id: str) -> TimeSeries | None:
        raise NotImplementedError
