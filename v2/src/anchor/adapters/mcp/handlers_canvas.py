"""MCP tool definitions backed by WorkspaceService.

Tool names keep the v1 `canvas_*` prefix so existing agent prompts continue
to work; every tool now takes `workspace_slug` as its first arg.
"""
from __future__ import annotations

import json
from typing import Any

from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.workspace.workspace import CommandError


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "canvas_get_state",
            "description": "Return the full canvas state (version, nodes, edges, metadata).",
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_slug": {"type": "string"}},
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_add_node",
            "description": "Add a node by node_type, label, x, y, parent, data.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                    "node_type": {"type": "string"},
                    "label": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "parent": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_update_node",
            "description": "Patch a node's fields.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "data": {"type": "object"},
                },
                "required": ["workspace_slug", "id"],
            },
        },
        {
            "name": "canvas_remove_node",
            "description": "Delete a node by id (cascades connected edges).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                },
                "required": ["workspace_slug", "id"],
            },
        },
        {
            "name": "canvas_add_edge",
            "description": "Connect two nodes (source, target, label, edge_type, data).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "label": {"type": "string"},
                    "edge_type": {"type": "string", "enum": ["floating", "anchored"]},
                    "data": {"type": "object"},
                },
                "required": ["workspace_slug", "source", "target"],
            },
        },
        {
            "name": "canvas_remove_edge",
            "description": "Delete an edge by id.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "id": {"type": "string"},
                },
                "required": ["workspace_slug", "id"],
            },
        },
        {
            "name": "canvas_clear",
            "description": "Wipe the canvas (cards + edges).",
            "inputSchema": {
                "type": "object",
                "properties": {"workspace_slug": {"type": "string"}},
                "required": ["workspace_slug"],
            },
        },
        {
            "name": "canvas_create_workspace",
            "description": "Create a new workspace folder.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": ["slug"],
            },
        },
        {
            "name": "canvas_list_workspaces",
            "description": "List all workspaces.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]


async def call_tool(svc: WorkspaceService, name: str, args: dict[str, Any]) -> str:
    try:
        if name == "canvas_get_state":
            return json.dumps(await svc.get_state(args["workspace_slug"]))
        if name == "canvas_create_workspace":
            return json.dumps(await svc.create_workspace(args["slug"], title=args.get("title", "")))
        if name == "canvas_list_workspaces":
            return json.dumps(await svc.list_workspaces())
        if name == "canvas_add_node":
            slug = args.pop("workspace_slug")
            state, env = await svc.add_node(slug, **args)
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_update_node":
            slug = args.pop("workspace_slug")
            node_id = args.pop("id")
            fields = {k: v for k, v in args.items() if v is not None}
            if {"x", "y"} <= fields.keys() and len(fields) == 2:
                state, env = await svc.move_node(slug, node_id, fields["x"], fields["y"])
            else:
                state, env = await svc.update_node(slug, node_id, fields)
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_remove_node":
            state, envelopes = await svc.remove_node(args["workspace_slug"], args["id"])
            return json.dumps({"events": [e.model_dump() for e in envelopes], "state": state.get_state()})
        if name == "canvas_add_edge":
            slug = args.pop("workspace_slug")
            state, env = await svc.add_edge(slug, **args)
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_remove_edge":
            state, env = await svc.remove_edge(args["workspace_slug"], args["id"])
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_clear":
            state, env = await svc.clear(args["workspace_slug"])
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
    except CommandError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"unknown tool: {name}"})
