"""CAD extension events emitted on the canvas EventBus."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class CadIngested(BaseModel):
    type: Literal["CadIngested"] = "CadIngested"
    cad_slug: str
    kind: str
    parameter_count: int = 0
    part_count: int = 0


class CadParameterChanged(BaseModel):
    """Emitted when an agent or user tweaks a parameter on a parametric model."""

    type: Literal["CadParameterChanged"] = "CadParameterChanged"
    cad_slug: str
    parameter_name: str
    old_value: float | int | str | bool | None = None
    new_value: float | int | str | bool


class CadIngestFailed(BaseModel):
    type: Literal["CadIngestFailed"] = "CadIngestFailed"
    filename: str
    error: str
