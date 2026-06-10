"""MCP tool definitions for the FMU extension.

Tool names use underscores because Claude Desktop rejects dots in MCP tool
names. Dotted names are still accepted as legacy aliases by ``call_tool``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anchor.extensions.anchor_fmus.core.services import FmuService

LEGACY_TOOL_ALIASES = {
    "fmu.inspect": "fmu_inspect",
    "fmu.list_models": "fmu_list_models",
    "fmu.get_model": "fmu_get_model",
    "fmu.simulate": "fmu_simulate",
    "fmu.get_results": "fmu_get_results",
    "fmu.list_simulations": "fmu_list_simulations",
}
LEGACY_TOOL_NAMES = set(LEGACY_TOOL_ALIASES)


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "fmu_inspect",
            "description": "Upload a .fmu file to anchor's data dir and parse modelDescription. "
                           "Returns the model: variables, causality, units, defaults.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "fmu_path": {"type": "string", "description": "absolute path to a .fmu file"},
                },
                "required": ["fmu_path"],
            },
        },
        {
            "name": "fmu_list_models",
            "description": "List every FMU known to this Anchor install with its variables.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "fmu_get_model",
            "description": "Return one FMU's model description by slug.",
            "inputSchema": {
                "type": "object",
                "properties": {"slug": {"type": "string"}},
                "required": ["slug"],
            },
        },
        {
            "name": "fmu_simulate",
            "description": "Run a simulation. Returns the simulation id; results stream via "
                           "SimulationCompleted events on the canvas event bus.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                    "parameter_overrides": {"type": "object"},
                    "stop_time": {"type": "number", "default": 1.0},
                    "output_interval": {"type": "number", "default": 0.01},
                },
                "required": ["slug"],
            },
        },
        {
            "name": "fmu_get_results",
            "description": "Return the time series for a completed simulation.",
            "inputSchema": {
                "type": "object",
                "properties": {"simulation_id": {"type": "string"}},
                "required": ["simulation_id"],
            },
        },
        {
            "name": "fmu_list_simulations",
            "description": "List simulation runs, optionally filtered to one FMU.",
            "inputSchema": {
                "type": "object",
                "properties": {"fmu_slug": {"type": "string"}},
            },
        },
    ]


async def call_tool(svc: FmuService, name: str, args: dict[str, Any]) -> str:
    name = LEGACY_TOOL_ALIASES.get(name, name)
    try:
        if name == "fmu_inspect":
            path = Path(args["fmu_path"])
            if not path.exists():
                return json.dumps({"error": f"FMU not found: {path}"})
            model = await svc.upload_and_inspect(path.read_bytes(), path.name)
            return model.model_dump_json(indent=2)
        if name == "fmu_list_models":
            models = await svc.list_models()
            return json.dumps([m.model_dump() for m in models], indent=2)
        if name == "fmu_get_model":
            model = await svc.get_model(args["slug"])
            if model is None:
                return json.dumps({"error": f"unknown FMU: {args['slug']}"})
            return model.model_dump_json(indent=2)
        if name == "fmu_simulate":
            run = await svc.simulate(
                args["slug"],
                parameter_overrides=args.get("parameter_overrides"),
                stop_time=float(args.get("stop_time", 1.0)),
                output_interval=float(args.get("output_interval", 0.01)),
            )
            return run.model_dump_json(indent=2)
        if name == "fmu_get_results":
            series = await svc.get_series(args["simulation_id"])
            if series is None:
                return json.dumps({"error": f"unknown simulation: {args['simulation_id']}"})
            return series.model_dump_json()
        if name == "fmu_list_simulations":
            runs = await svc.list_simulations(args.get("fmu_slug"))
            return json.dumps([r.model_dump() for r in runs], indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"error": f"unknown tool: {name}"})
