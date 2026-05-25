"""FMU domain schemas — pure data, no I/O."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from anchor.core.ids import new_id

# Variable kinds from the FMI standard
Causality = Literal["input", "output", "parameter", "calculatedParameter", "local", "independent"]
Variability = Literal["constant", "fixed", "tunable", "discrete", "continuous"]


class FmuVariable(BaseModel):
    """One variable in an FMU's modelDescription.xml."""

    name: str
    causality: Causality
    variability: Variability = "continuous"
    description: str = ""
    unit: str | None = None
    start: float | str | bool | None = None
    type: Literal["Real", "Integer", "Boolean", "String"] = "Real"


class FmuModel(BaseModel):
    """An ingested FMU — its modelDescription summary."""

    slug: str
    filename: str
    model_name: str = ""
    description: str = ""
    fmi_version: str = "2.0"
    platforms: list[str] = Field(default_factory=list)
    variables: list[FmuVariable] = Field(default_factory=list)
    # ``true`` when the model description came from the offline-demo
    # ``FakeFmuRuntime`` rather than a real FMU runtime (FMPy). UI badges
    # and CLI output use this to make the synthetic nature obvious so an
    # engineer doesn't mistake demo data for a real simulation.
    synthetic: bool = False

    def inputs(self) -> list[FmuVariable]:
        return [v for v in self.variables if v.causality == "input"]

    def outputs(self) -> list[FmuVariable]:
        return [v for v in self.variables if v.causality == "output"]

    def parameters(self) -> list[FmuVariable]:
        return [v for v in self.variables if v.causality in ("parameter", "calculatedParameter")]


class SimulationRun(BaseModel):
    """A completed (or in-progress) simulation."""

    id: str = Field(default_factory=new_id)
    fmu_slug: str
    started_at: float = 0.0
    completed_at: float | None = None
    status: Literal["running", "completed", "failed"] = "running"
    stop_time: float = 1.0
    output_interval: float = 0.01
    parameter_overrides: dict[str, float] = Field(default_factory=dict)
    error: str | None = None
    # ``true`` when the result came from FakeFmuRuntime. Carried separately
    # from the model flag so a real FMU run against a synthetic-marked
    # model (mixed mode in test harnesses) is still distinguishable.
    synthetic: bool = False


class TimeSeries(BaseModel):
    """A simulation result: one column per variable, one row per time point."""

    simulation_id: str
    time: list[float]
    variables: dict[str, list[float]] = Field(default_factory=dict)
    synthetic: bool = False


# ── Source-ref kinds for OIP ────────────────────────────────────────────


class FmuVariableRef(BaseModel):
    """SourceRef pointing at a single variable inside an FMU model."""

    kind: Literal["fmu-variable"] = "fmu-variable"
    fmu_slug: str
    variable_name: str
    causality: Causality | None = None


class FmuSimulationTimeRef(BaseModel):
    """SourceRef pointing at a value at a specific time in a simulation run."""

    kind: Literal["fmu-simulation-time"] = "fmu-simulation-time"
    simulation_id: str
    time_seconds: float
    variable_name: str | None = None


# ── Node `data` schemas (registered with NodeTypeRegistry) ──────────────


class FmuModelNodeData(BaseModel):
    """Data for an `fmu:model` node — a card representing an FMU on the canvas."""

    fmu_slug: str
    model_name: str = ""
    inputs: list[str] = Field(default_factory=list)   # variable names
    outputs: list[str] = Field(default_factory=list)
    parameters: list[str] = Field(default_factory=list)


class FmuPlotNodeData(BaseModel):
    """Data for an `fmu:plot` node — a Recharts plot."""

    simulation_id: str
    variables: list[str]
    title: str = ""


class FmuVariableNodeData(BaseModel):
    """Data for an `fmu:variable` node — a single variable + current value."""

    fmu_slug: str
    variable_name: str
    causality: Causality
    current_value: Any = None
