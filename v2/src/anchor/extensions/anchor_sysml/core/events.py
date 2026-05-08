"""SysML extension events emitted on the canvas EventBus.

Kept narrow — Phase 1 emits one event per ``render`` and one per ``export``.
Per-node/edge events would just duplicate the canvas-primitive events that
``WorkspaceService`` already publishes for every ``add_node`` / ``add_edge``.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SysmlRendered(BaseModel):
    type: Literal["SysmlRendered"] = "SysmlRendered"
    workspace_slug: str
    node_count: int = 0
    edge_count: int = 0
    diagnostic_count: int = 0
    filename: str | None = None


class SysmlExported(BaseModel):
    type: Literal["SysmlExported"] = "SysmlExported"
    workspace_slug: str
    char_count: int = 0


class SysmlRenderFailed(BaseModel):
    type: Literal["SysmlRenderFailed"] = "SysmlRenderFailed"
    workspace_slug: str
    error: str
