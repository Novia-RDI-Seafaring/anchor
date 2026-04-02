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
    """Legacy flat property — kept for backward compat."""
    key: str
    value: str
    unit: str = ""
    group: str = ""
    left_label: str = ""
    left_value: str = ""
    right_label: str = ""
    right_value: str = ""
    comparison_status: str = ""
    ref_filename: str = ""
    ref_page: int = 0
    ref_bbox: list[float] = Field(default_factory=list)
    ref_highlights: list[SourceHighlight] = Field(default_factory=list)


class ParameterSource(BaseModel):
    """Source reference for a single parameter value."""
    doc_id: str = ""
    filename: str = ""
    page: int = 0
    bbox: list[float] = Field(default_factory=list)


class ParameterRow(BaseModel):
    """One row in a parameter table."""
    parameter: str       # e.g. "LKH-5", "Temperature range"
    value: str           # e.g. "600", "-10 to +140"
    unit: str = ""       # e.g. "kPa", "°C"
    source: ParameterSource = Field(default_factory=ParameterSource)


class ParameterSection(BaseModel):
    """A named group of parameter rows."""
    name: str            # e.g. "Max inlet pressure", "Temperature"
    rows: list[ParameterRow] = Field(default_factory=list)


class FmuVariable(BaseModel):
    name: str
    causality: str = ""   # input | output | parameter | local
    variability: str = ""
    start: str = ""
    unit: str = ""
    description: str = ""


class CanvasNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    node_type: Literal["concept", "topic", "fact", "spec", "document", "source", "entity", "category", "fmu", "plot", "image", "funnel", "area", "model"]  # source/entity/category kept for backward compat
    status: NodeStatus = "found"
    last_updated_run_id: str = ""
    color: str = ""  # user-set accent color (e.g. "violet", "blue", "emerald", "amber", "rose", "indigo", "slate")
    # topic fields
    title: str = ""
    # fact fields
    text: str = ""
    # spec fields
    spec_title: str = ""
    properties: list[SpecProperty] = Field(default_factory=list)  # legacy flat properties
    parameter_sections: list[ParameterSection] = Field(default_factory=list)  # new structured sections
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
    # image node fields
    image_filename: str = ""
    image_page: int = 0
    image_bbox: list[float] = Field(default_factory=list)  # [l, t, r, b] cropped region, empty = full page
    image_highlights: list[str] = Field(default_factory=list)  # text phrases to highlight on the rendered image
    image_caption: str = ""
    # plot node fields
    plot_job_id: str = ""
    plot_fmu_filename: str = ""
    plot_signal_names: list[str] = Field(default_factory=list)
    plot_stop_time: float = 10.0
    plot_param_values: dict[str, float] = Field(default_factory=dict)
    # funnel node fields
    funnel_label: str = ""
    # area node fields
    area_label: str = ""
    area_width: float = 600.0
    area_height: float = 400.0
    # generic canvas dimensions
    width: float = 0.0
    height: float = 0.0
    # parent-child (for area containment)
    parent_id: str = ""


class Relation(BaseModel):
    from_id: str
    to_id: str
    label: str = ""
    source_handle: str = ""
    target_handle: str = ""
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
    workspace_doc_ids: list[str] = Field(default_factory=list)


__all__ = ["Canvas", "CanvasNode", "Relation", "SourceHighlight", "SpecProperty", "ParameterSource", "ParameterRow", "ParameterSection", "NodeStatus", "FmuVariable"]
