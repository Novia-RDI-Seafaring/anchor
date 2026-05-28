"""Filesystem-backed FmuStore.

On-disk layout (mirrors the OIP convention):
    <data-dir>/fmus/
        bronze/<slug>.fmu              raw FMU files
        models/<slug>.json             FmuModel summaries (modelDescription)
        simulations/<id>/run.json      SimulationRun metadata
        simulations/<id>/series.json   TimeSeries data
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import aiofiles

from anchor.core.ids import slugify
from anchor.core.upload_safety import assert_within
from anchor.extensions.anchor_fmus.core.ports import FmuStore
from anchor.extensions.anchor_fmus.core.schemas import (
    FmuModel,
    SimulationRun,
    TimeSeries,
)


class FsFmuStore(FmuStore):
    def __init__(self, data_dir: Path) -> None:
        root = Path(data_dir) / "fmus"
        self.root = root
        self.bronze = root / "bronze"
        self.models = root / "models"
        self.simulations = root / "simulations"
        for d in (self.bronze, self.models, self.simulations):
            d.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def stash_fmu(self, fmu_bytes: bytes, filename: str) -> Path:
        # Defence-in-depth: the HTTP/MCP layer should have normalised the
        # filename via safe_upload_name, but stores get called from places
        # that side-step the adapter (CLI scripts, tests, future agents).
        # Slugify the stem so we never write a client-controlled directory
        # component, and verify the resolved target stays under self.bronze.
        stem = Path(filename).stem or "upload"
        target = self.bronze / f"{slugify(stem)}.fmu"
        async with self._lock:
            assert_within(target, self.bronze)
            async with aiofiles.open(target, "wb") as f:
                await f.write(fmu_bytes)
        return target

    async def get_fmu_path(self, slug: str) -> Path | None:
        for path in self.bronze.iterdir():
            if path.is_file() and slugify(path.stem) == slug:
                return path
        return None

    async def list_fmus(self) -> list[FmuModel]:
        out: list[FmuModel] = []
        for path in sorted(self.models.glob("*.json")):
            out.append(FmuModel.model_validate_json(path.read_text()))
        return out

    async def write_model_summary(self, slug: str, model: FmuModel) -> Path:
        target = self.models / f"{slug}.json"
        async with aiofiles.open(target, "w") as f:
            await f.write(model.model_dump_json(indent=2))
        return target

    async def get_model(self, slug: str) -> FmuModel | None:
        path = self.models / f"{slug}.json"
        if not path.exists():
            return None
        return FmuModel.model_validate_json(path.read_text())

    async def write_simulation(self, run: SimulationRun, series: TimeSeries) -> Path:
        sim_dir = self.simulations / run.id
        sim_dir.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(sim_dir / "run.json", "w") as f:
            await f.write(run.model_dump_json(indent=2))
        async with aiofiles.open(sim_dir / "series.json", "w") as f:
            await f.write(series.model_dump_json())
        return sim_dir / "run.json"

    async def list_simulations(self, fmu_slug: str | None = None) -> list[SimulationRun]:
        out: list[SimulationRun] = []
        for sim_dir in sorted(self.simulations.iterdir()):
            run_path = sim_dir / "run.json"
            if not run_path.exists():
                continue
            run = SimulationRun.model_validate_json(run_path.read_text())
            if fmu_slug is None or run.fmu_slug == fmu_slug:
                out.append(run)
        return out

    async def get_series(self, simulation_id: str) -> TimeSeries | None:
        path = self.simulations / simulation_id / "series.json"
        if not path.exists():
            return None
        return TimeSeries.model_validate_json(path.read_text())
