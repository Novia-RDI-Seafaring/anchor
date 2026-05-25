"""MCP tools exposed by anchor-cad: namespaced `cad.*` when surfaced to clients.

Tool names here are unprefixed — the consumer adds the `tools_namespace`
prefix from the OIP manifest. So inside this server the tool is `inspect`;
clients see `cad.inspect`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anchor.extensions.anchor_cad.core.services import CadService

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "inspect",
        "description": "Ingest a CAD file (STL/OBJ/STEP/IGES/glTF/JSCAD/OpenSCAD) and emit a CadModel summary.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cad_path": {"type": "string", "description": "Absolute path to the file."},
            },
            "required": ["cad_path"],
        },
    },
    {
        "name": "list_models",
        "description": "List all CAD models that have been ingested.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_model",
        "description": "Get a specific CadModel by slug.",
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
    },
    {
        "name": "set_parameter",
        "description": (
            "Tweak a named parameter on a parametric CAD model. Updates the "
            "stored summary and emits CadParameterChanged on the bus so any "
            "3D viewport subscribed to the canvas re-renders. (Re-evaluation "
            "of the actual geometry is a follow-on.)"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "parameter_name": {"type": "string"},
                "value": {"description": "New value for the parameter."},
            },
            "required": ["slug", "parameter_name", "value"],
        },
    },
]


async def call_tool(name: str, arguments: dict[str, Any], *, service: CadService) -> str:
    if name == "inspect":
        path = Path(arguments["cad_path"])
        cad_bytes = path.read_bytes()
        model = await service.upload_and_inspect(cad_bytes, path.name)
        return model.model_dump_json()
    if name == "list_models":
        models = await service.list_models()
        return json.dumps([m.model_dump() for m in models])
    if name == "get_model":
        model = await service.get_model(arguments["slug"])
        return model.model_dump_json() if model else "null"
    if name == "set_parameter":
        model = await service.set_parameter(
            arguments["slug"], arguments["parameter_name"], arguments["value"],
        )
        return model.model_dump_json()
    raise ValueError(f"unknown tool: {name}")
