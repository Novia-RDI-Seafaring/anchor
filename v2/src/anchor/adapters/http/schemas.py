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


class IngestUploadResponse(BaseModel):
    slug: str
    job_id: str
    status: str = "started"
