"""Edge — connection between two cards.

`edge_type` is a free string by design; the application registers any
domain-specific edge-type validators via `core.workspace.edge_types`. The
two structural defaults are `floating` (auto-routed) and `anchored`
(explicit handle-to-handle), but the system doesn't bake those in as the
only options.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from anchor.core.ids import new_id


class Edge(BaseModel):
    id: str = Field(default_factory=new_id)
    source: str
    target: str
    label: str = ""
    edge_type: str = "floating"
    data: dict[str, Any] = Field(default_factory=dict)
