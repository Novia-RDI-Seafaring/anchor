"""Canvas state used by the live evidence-mapping agent."""
from __future__ import annotations

from typing import Literal
from uuid import uuid4

NodeStatus = Literal["pending", "searching", "found", "partial", "not_found"]

from pydantic import BaseModel, Field


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


class CanvasNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    node_type: Literal["entity", "category", "topic", "fact", "source", "spec"]
    status: NodeStatus = "pending"
    last_updated_run_id: str = ""
    # topic fields
    title: str = ""
    # fact fields
    text: str = ""
    # source fields
    filename: str = ""
    page: int = 0                                        # primary / first page (legacy)
    bbox: list[float] = Field(default_factory=list)      # primary bbox (legacy)
    highlights: list[SourceHighlight] = Field(default_factory=list)  # ordered list of page+bbox refs
    # spec fields
    spec_title: str = ""
    properties: list[SpecProperty] = Field(default_factory=list)


class Relation(BaseModel):
    from_id: str
    to_id: str
    label: str = ""


class Canvas(BaseModel):
    nodes: list[CanvasNode] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    last_updated_run_id: str = ""

__all__ = ["Canvas", "CanvasNode", "Relation", "SourceHighlight", "SpecProperty", "NodeStatus"]
