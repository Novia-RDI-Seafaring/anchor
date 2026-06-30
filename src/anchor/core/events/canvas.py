"""Canvas event types — what happens on a workspace.

Each event is a thin Pydantic model carrying the type literal + payload shape.
The actual transport/persistence wraps these in `DomainEvent` envelopes.

Vocabulary: nodes & edges (matches ReactFlow, the wire format, HTTP routes,
and the MCP tool names). The v2 refactor briefly used `Card*` event names;
those are renamed to `Node*` here for full consistency.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CanvasEventType = Literal[
    "NodeAdded",
    "NodeRemoved",
    "NodeMoved",
    "NodeResized",
    "NodeUpdated",
    "NodeReparented",
    "EdgeAdded",
    "EdgeRemoved",
    "EdgeUpdated",
    "CanvasCleared",
    "CanvasSnapshot",
    "ReferenceCreated",
    "ReferenceAttached",
]


class NodeAdded(BaseModel):
    type: Literal["NodeAdded"] = "NodeAdded"
    id: str
    node_type: str = "concept"
    label: str = ""
    x: float = 0
    y: float = 0
    width: float | None = None
    height: float | None = None
    parent: str | None = None
    data: dict[str, Any] = {}


class NodeRemoved(BaseModel):
    type: Literal["NodeRemoved"] = "NodeRemoved"
    id: str


class NodeMoved(BaseModel):
    type: Literal["NodeMoved"] = "NodeMoved"
    id: str
    x: float
    y: float


class NodeResized(BaseModel):
    type: Literal["NodeResized"] = "NodeResized"
    id: str
    width: float
    height: float


class NodeUpdated(BaseModel):
    type: Literal["NodeUpdated"] = "NodeUpdated"
    id: str
    fields: dict[str, Any]


class NodeReparented(BaseModel):
    type: Literal["NodeReparented"] = "NodeReparented"
    id: str
    parent: str | None


class EdgeAdded(BaseModel):
    type: Literal["EdgeAdded"] = "EdgeAdded"
    id: str
    source: str
    target: str
    label: str = ""
    edge_type: str = "floating"
    # Optional handle ids on the source/target nodes (ReactFlow handle ids).
    # When present the edge pins to that specific handle instead of routing
    # node-to-node; row-level evidence edges live here. Snake-case aliases
    # are accepted so adapters that prefer that shape (CLI flags) work.
    sourceHandle: str | None = Field(default=None, alias="source_handle")
    targetHandle: str | None = Field(default=None, alias="target_handle")
    data: dict[str, Any] = {}

    model_config = {"populate_by_name": True}


class EdgeRemoved(BaseModel):
    type: Literal["EdgeRemoved"] = "EdgeRemoved"
    id: str


class EdgeUpdated(BaseModel):
    type: Literal["EdgeUpdated"] = "EdgeUpdated"
    id: str
    fields: dict[str, Any]


class CanvasCleared(BaseModel):
    type: Literal["CanvasCleared"] = "CanvasCleared"


class CanvasSnapshot(BaseModel):
    """Full state — used as a replay checkpoint."""

    type: Literal["CanvasSnapshot"] = "CanvasSnapshot"
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}


class ReferenceCreated(BaseModel):
    """A reference (citation) was added to the canvas bibliography.

    ``reference`` is the full stored shape (id already assigned). The reducer
    appends it to ``metadata['references']``. Canvas-scoped for now; the event
    name is deliberately store-agnostic so a project-level store can reuse it.
    """

    type: Literal["ReferenceCreated"] = "ReferenceCreated"
    reference: dict[str, Any]


class ReferenceAttached(BaseModel):
    """A reference was attached to a node (and optionally a spec row).

    Carries the linkage so the target node/row resolves back to the
    reference by id and carries the reference's ``source_ref`` (which drives
    the value-level highlight from #145/#200). ``row_index`` is optional and
    targets one row inside a spec node's ``data.rows``.
    """

    type: Literal["ReferenceAttached"] = "ReferenceAttached"
    reference_id: str
    node_id: str
    row_index: int | None = None
    source_ref: dict[str, Any]


class ReferenceRemoved(BaseModel):
    """A reference was removed from the canvas bibliography.

    ``reference_id`` names the entry to drop from ``metadata['references']``.
    The reducer is a no-op when the id is absent (idempotent). Detaching the
    reference from any node/row it was attached to is out of scope for this
    event: the pointer is a cached copy and is cleaned up separately (slice 4).
    """

    type: Literal["ReferenceRemoved"] = "ReferenceRemoved"
    reference_id: str


class ReferenceUpdated(BaseModel):
    """A reference's ``label`` was edited in the canvas bibliography.

    Only the human caption changes; the ``source_ref`` locator is immutable
    here so the schema stays stable (#147 slice 3). ``label`` may be ``None``
    to clear the caption.
    """

    type: Literal["ReferenceUpdated"] = "ReferenceUpdated"
    reference_id: str
    label: str | None = None
