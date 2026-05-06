"""Domain events for the FMU extension."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class FmuInspected(BaseModel):
    type: Literal["FmuInspected"] = "FmuInspected"
    fmu_slug: str
    variable_count: int


class SimulationStarted(BaseModel):
    type: Literal["SimulationStarted"] = "SimulationStarted"
    simulation_id: str
    fmu_slug: str
    parameter_overrides: dict[str, float] = {}


class SimulationCompleted(BaseModel):
    type: Literal["SimulationCompleted"] = "SimulationCompleted"
    simulation_id: str
    fmu_slug: str
    duration_ms: int
    summary: dict[str, Any] = {}


class SimulationFailed(BaseModel):
    type: Literal["SimulationFailed"] = "SimulationFailed"
    simulation_id: str
    fmu_slug: str
    error: str


class SimulationProgress(BaseModel):
    """High-frequency, bus-only — never persisted."""

    type: Literal["SimulationProgress"] = "SimulationProgress"
    simulation_id: str
    current_time: float
    stop_time: float
