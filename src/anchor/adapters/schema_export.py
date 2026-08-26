"""Small schema export used to catch Python/web wire drift."""
from __future__ import annotations

from typing import Any, get_args

from pydantic import BaseModel

from anchor.core.events.canvas import CanvasEventType
from anchor.core.events.envelope import DomainEvent
from anchor.core.workspace.edges import Edge
from anchor.core.workspace.nodes import Node
from anchor.core.workspace.workspace import Workspace, WorkspaceMeta

SCHEMA_EXPORT_VERSION = 1


def _model_snapshot(model: type[BaseModel]) -> dict[str, Any]:
    fields = model.model_fields
    return {
        "fields": list(fields),
        "required": [name for name, field in fields.items() if field.is_required()],
    }


def export_core_wire_schema() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_EXPORT_VERSION,
        "models": {
            "Node": _model_snapshot(Node),
            "Edge": _model_snapshot(Edge),
            "Workspace": _model_snapshot(Workspace),
            "WorkspaceMeta": _model_snapshot(WorkspaceMeta),
            "DomainEvent": _model_snapshot(DomainEvent),
        },
        "canvas_event_types": list(get_args(CanvasEventType)),
    }
