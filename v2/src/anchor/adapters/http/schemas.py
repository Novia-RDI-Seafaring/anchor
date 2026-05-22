"""HTTP request/response Pydantic schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CreateWorkspaceRequest(BaseModel):
    slug: str
    title: str = ""


class AddNodeRequest(BaseModel):
    id: str | None = None
    node_type: str = "concept"
    label: str = ""
    x: float = 0
    y: float = 0
    width: float | None = None
    height: float | None = None
    parent: str | None = None
    data: dict[str, Any] = {}


class UpdateNodeRequest(BaseModel):
    label: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    parent: str | None = None
    data: dict[str, Any] | None = None


class AddEdgeRequest(BaseModel):
    id: str | None = None
    source: str
    target: str
    label: str = ""
    edge_type: str = "floating"
    data: dict[str, Any] = {}


class UpdateEdgeRequest(BaseModel):
    """Partial edge update. Any field omitted (= None) is left unchanged.

    Mirrors UpdateNodeRequest's shape so HTTP/MCP/CLI clients have a
    consistent patch contract."""
    label: str | None = None
    edge_type: str | None = None
    sourceHandle: str | None = None
    targetHandle: str | None = None
    data: dict[str, Any] | None = None


class IngestUploadResponse(BaseModel):
    slug: str
    job_id: str
    status: str = "started"


class SnapshotRequest(BaseModel):
    format: str = "png"
    viewport: tuple[int, int] | None = None
    full_page: bool = True


class OrganizeSubtreeRequest(BaseModel):
    root_id: str
    orientation: str = "vertical"
    algo: str = "dagre"


class AlignNodesRequest(BaseModel):
    """Body of POST /api/workspaces/{slug}/align — match `align_nodes` core args."""
    ids: list[str]
    anchor: str = "top"


class DistributeNodesRequest(BaseModel):
    """Body of POST /api/workspaces/{slug}/distribute."""
    ids: list[str]
    axis: str = "horizontal"


class CreateSubCanvasRequest(BaseModel):
    """Body for ``POST /api/workspaces/{parent_slug}/sub-canvas``.

    Convenience composite: provisions a child workspace and drops a
    ``canvas``-typed linking node onto the parent in one server-side step.
    """

    slug: str
    title: str = ""
    x: float = 0.0
    y: float = 0.0
