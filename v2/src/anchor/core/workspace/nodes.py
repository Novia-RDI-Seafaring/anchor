"""Node — the canvas's graph node. Pure pydantic model.

`node_type` is a free string by design (no Literal). Application code
registers domain-specific types in `core.workspace.node_types.NodeTypeRegistry`,
and the registry decides what's valid, how the data field is shaped, and
how the frontend renders it. Core does not enumerate node types — that's
a v1 anti-pattern (19 hard-coded variants) that this rewrite fixes.

Cross-cutting structural concerns are top-level fields (locked, visible,
layer, opacity) so they're type-checked and uniformly handled across every
node_type. Domain-specific payload (spec rows, fmu variables, image url, …)
goes in `data`.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from anchor.core.ids import new_id

NodeLayer = Literal["background", "content", "annotation"]


class Node(BaseModel):
    """A node on the canvas. `node_type` is open-ended; see `node_types.py`."""

    id: str = Field(default_factory=new_id)
    node_type: str = "concept"
    label: str = ""
    x: float = 0
    y: float = 0
    width: float | None = None
    height: float | None = None
    parent: str | None = None

    # Cross-cutting structural concerns — applied uniformly by the renderer
    # and the validator regardless of node_type. Promoted out of `data` for
    # type safety.
    locked: bool = False
    visible: bool = True
    layer: NodeLayer = "content"
    opacity: float | None = None

    # Domain-specific payload — shape determined by node_type's registered
    # data_schema in NodeTypeRegistry.
    data: dict[str, Any] = Field(default_factory=dict)
