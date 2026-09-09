"""HTTP request/response Pydantic schemas."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from anchor.core.events.actor import Actor


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""


class RenameProjectRequest(BaseModel):
    new: str


class CreateWorkspaceRequest(BaseModel):
    slug: str
    title: str = ""


class RenameWorkspaceRequest(BaseModel):
    """Body for ``PATCH /api/workspaces/{slug}``.

    The slug (directory id) is immutable. ``title`` updates the display
    title (the historic rename op). ``review_mode`` toggles the
    workspace's review opt-in (#324): when true, agent-created nodes get
    ``data.review = {state: "proposed", ...}`` stamped server-side.
    Both fields are optional; at least one must be present.
    """
    title: str | None = None
    review_mode: bool | None = None


class AddNodeRequest(BaseModel):
    id: str | None = None
    # `node_type` is canonical; `type` is accepted as an alias so a client
    # can write back the field name it reads from canvas state (#186).
    node_type: str | None = None
    type: str | None = None
    label: str = ""
    # x/y default to None so the server can tell "no coordinates given"
    # (→ auto-place) from "placed at 0,0". `place="auto"` forces auto-place
    # even when coordinates are present (#189).
    x: float | None = None
    y: float | None = None
    place: str | None = None
    width: float | None = None
    height: float | None = None
    parent: str | None = None
    locked: bool | None = None
    visible: bool | None = None
    layer: Literal["background", "content", "annotation"] | None = None
    opacity: float | None = None
    data: dict[str, Any] = {}
    # Explicit actor attribution override (#322). Omitted → the HTTP
    # default `{kind: "human", label: "browser"}` applies.
    actor: Actor | None = None


class UpdateNodeRequest(BaseModel):
    label: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    parent: str | None = None
    locked: bool | None = None
    visible: bool | None = None
    layer: Literal["background", "content", "annotation"] | None = None
    opacity: float | None = None
    data: dict[str, Any] | None = None
    # Explicit actor attribution override (#322).
    actor: Actor | None = None


class AddEdgeRequest(BaseModel):
    id: str | None = None
    source: str
    target: str
    label: str = ""
    # `edge_type` is canonical; `type` accepted as an alias (#186).
    edge_type: str | None = None
    type: str | None = None
    # Optional ReactFlow handle ids. When set, pin the edge to that specific
    # handle on the source/target node (e.g. spec-row → document-region).
    sourceHandle: str | None = None
    targetHandle: str | None = None
    data: dict[str, Any] = {}
    # Explicit actor attribution override (#322).
    actor: Actor | None = None


class UpdateEdgeRequest(BaseModel):
    """Partial edge update. Any field omitted (= None) is left unchanged.

    Mirrors UpdateNodeRequest's shape so HTTP/MCP/CLI clients have a
    consistent patch contract."""
    label: str | None = None
    edge_type: str | None = None
    type: str | None = None  # alias for edge_type (#186)
    sourceHandle: str | None = None
    targetHandle: str | None = None
    data: dict[str, Any] | None = None
    # Explicit actor attribution override (#322).
    actor: Actor | None = None


class IngestUploadResponse(BaseModel):
    slug: str
    job_id: str
    # "started" when the server ingests directly; "awaiting_agent" when the
    # project's ingestion is harness-driven and a drop_to_ingest intent was
    # enqueued for the agent to pick up (issue #148).
    status: str = "started"
    intent_id: str | None = None


class SnapshotRequest(BaseModel):
    format: str = "png"
    viewport: tuple[int, int] | None = None
    full_page: bool = True


class OrganizeSubtreeRequest(BaseModel):
    root_id: str
    orientation: str = "vertical"
    algo: str = "dagre"
    # Edge-walk policy: "outgoing" (parent → child), "incoming" (reports-to,
    # subordinate → boss), or "any" (undirected — v1 default). Default "any"
    # preserves the original UX; callers that want strict descendant scoping
    # pick "incoming" or "outgoing" depending on the canvas convention.
    direction: str = "any"


class AlignNodesRequest(BaseModel):
    """Body of POST /api/workspaces/{slug}/align — match `align_nodes` core args."""
    ids: list[str]
    anchor: str = "top"


class DistributeNodesRequest(BaseModel):
    """Body of POST /api/workspaces/{slug}/distribute."""
    ids: list[str]
    axis: str = "horizontal"


class CreateReferenceRequest(BaseModel):
    """Body for ``POST /api/workspaces/{slug}/references``.

    ``source_ref`` is the locator into a source document: ``{slug, page}`` are
    required, ``bbox`` / ``region_id`` / ``detail`` are optional. ``created_by``
    is ``"human"`` (default) or ``"agent"``."""

    source_ref: dict[str, Any]
    label: str | None = None
    created_by: str = "human"


class AttachReferenceRequest(BaseModel):
    """Body for ``POST /api/workspaces/{slug}/references/{id}/attach``.

    ``node_id`` names the target node; ``row_index`` optionally targets one
    row inside a spec node's ``data.rows``."""

    node_id: str
    row_index: int | None = None


class UpdateReferenceRequest(BaseModel):
    """Body for ``PATCH /api/workspaces/{slug}/references/{id}``.

    Only the human caption (``label``) is editable; the ``source_ref`` locator
    is immutable. ``label`` may be ``null`` to clear the caption."""

    label: str | None = None


class CreateSubCanvasRequest(BaseModel):
    """Body for ``POST /api/workspaces/{parent_slug}/sub-canvas``.

    Convenience composite: provisions a child workspace and drops a
    ``canvas``-typed linking node onto the parent in one server-side step.
    """

    slug: str
    title: str = ""
    x: float = 0.0
    y: float = 0.0
