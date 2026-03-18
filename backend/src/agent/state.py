"""Canvas state used by the live evidence-mapping agent."""
from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


NodeStatus = Literal["pending", "searching", "found", "partial", "not_found"]


class SourceHighlight(BaseModel):
    page: int
    bbox: list[float] = Field(default_factory=list)  # [l, t, r, b]


class SpecProperty(BaseModel):
    key: str
    value: str
    unit: str = ""
    left_label: str = ""
    left_value: str = ""
    right_label: str = ""
    right_value: str = ""
    comparison_status: str = ""


class FmuVariable(BaseModel):
    name: str
    causality: str = ""   # input | output | parameter | local
    variability: str = ""
    start: str = ""
    unit: str = ""
    description: str = ""


class CanvasNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    node_type: Literal["concept", "topic", "fact", "spec", "source", "entity", "category", "fmu", "plot"]  # source/entity/category kept for backward compat
    status: NodeStatus = "found"
    last_updated_run_id: str = ""
    # topic fields
    title: str = ""
    # fact fields
    text: str = ""
    # spec fields
    spec_title: str = ""
    properties: list[SpecProperty] = Field(default_factory=list)
    # deprecated evidence fields (kept for backward compat loading old states)
    filename: str = ""
    page: int = 0
    bbox: list[float] = Field(default_factory=list)
    highlights: list[SourceHighlight] = Field(default_factory=list)
    # fmu node fields
    fmu_filename: str = ""
    fmu_model_name: str = ""
    fmu_variables: list[FmuVariable] = Field(default_factory=list)
    fmu_param_values: dict[str, str] = Field(default_factory=dict)
    # plot node fields
    plot_job_id: str = ""
    plot_fmu_filename: str = ""
    plot_signal_names: list[str] = Field(default_factory=list)
    plot_stop_time: float = 10.0


class Relation(BaseModel):
    from_id: str
    to_id: str
    label: str = ""
    # Evidence metadata — populated when this edge connects a fact/spec to a document node (__doc_{id})
    document_id: str = ""
    page: int = 0
    bbox: list[float] = Field(default_factory=list)
    highlights: list[SourceHighlight] = Field(default_factory=list)


class Canvas(BaseModel):
    nodes: list[CanvasNode] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    last_updated_run_id: str = ""
    active_document_id: str | None = None


__all__ = ["Canvas", "CanvasNode", "Relation", "SourceHighlight", "SpecProperty", "NodeStatus", "FmuVariable"]
