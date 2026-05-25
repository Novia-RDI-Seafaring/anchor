"""FakeFmuRuntime — used in tests + as an offline demo runtime.

Returns canned model descriptions and synthetic time series so the FMU
extension can be exercised end-to-end without FMPy installed. Real
runtime (FmpyRuntime) lands in `fmpy_runtime.py` and is opt-in via
the `fmpy` extra.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from anchor.extensions.anchor_fmus.core.ports import FmuRuntime
from anchor.extensions.anchor_fmus.core.schemas import (
    FmuModel,
    FmuVariable,
    SimulationRun,
    TimeSeries,
)


class FakeFmuRuntime(FmuRuntime):
    """A pretend FMU runtime: every FMU has the same canned shape; simulation
    produces a smooth sinusoid for each output variable. Useful for
    extension tests, frontend dev, demos without FMPy.
    """

    synthetic = True

    def __init__(self, model_template: FmuModel | None = None) -> None:
        self._template = model_template or FmuModel(
            slug="",  # filled in by service from filename
            filename="",
            model_name="FakeModel",
            description="Synthetic test FMU",
            fmi_version="2.0",
            platforms=["fake"],
            variables=[
                FmuVariable(name="time", causality="independent"),
                FmuVariable(name="temp_in", causality="input", unit="degC", start=20.0),
                FmuVariable(name="mass_in", causality="input", unit="kg/s", start=1.0),
                FmuVariable(name="pump_value", causality="parameter", unit="kg/s", start=2.0),
                FmuVariable(name="temp_out", causality="output", unit="degC"),
                FmuVariable(name="mass_out", causality="output", unit="kg/s"),
            ],
        )

    async def inspect(self, fmu_path: Path) -> FmuModel:
        return self._template.model_copy(update={"filename": fmu_path.name})

    async def simulate(
        self,
        fmu_path: Path,
        *,
        run: SimulationRun,
        on_progress: object | None = None,
    ) -> TimeSeries:
        # A simple synthetic simulation: generate sinusoids for each output
        # at the requested output_interval, modulated by parameter overrides.
        n = max(2, int(run.stop_time / run.output_interval) + 1)
        time = [i * run.output_interval for i in range(n)]
        amp = run.parameter_overrides.get("pump_value", 2.0)
        phase = run.parameter_overrides.get("temp_in", 20.0)

        outputs = {
            "temp_out": [phase + 5 * math.sin(2 * math.pi * 0.5 * t) for t in time],
            "mass_out": [amp * (1 + 0.1 * math.cos(2 * math.pi * 1.0 * t)) for t in time],
        }
        return TimeSeries(simulation_id=run.id, time=time, variables=outputs)
