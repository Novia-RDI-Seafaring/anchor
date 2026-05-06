"""anchor_fmus extension — OIP-compliant FMU producer + canvas integration.

This module is the entry point an OIP-aware consumer (Anchor's canvas, today)
calls to register the extension. Returns the manifest + the wiring callbacks.

Until canvas core grows a formal `register_extension(...)` API in v0.3, the
hosting application (anchor's CLI/server) imports this module and threads the
manifest through `extensions list` and the wiring through its MCP server.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from anchor import __version__

NAME = "anchor-fmus"
DISPLAY_NAME = "Anchor FMUs"
VERSION = __version__
REQUIRES_CANVAS = ">=0.2,<0.3"
TOOLS_NAMESPACE = "fmu"


def manifest(data_dir: Path | None = None) -> dict[str, Any]:
    """The OIP manifest this extension advertises.

    Producers ship one of these to declare what they ingest, what they
    produce, and how a consumer invokes them. See OIP.md for the schema.
    """
    return {
        "oip_version": "0.1",
        "producer": {
            "name": NAME,
            "display_name": DISPLAY_NAME,
            "version": VERSION,
            "homepage": "https://github.com/Novia-RDI-Seafaring/anchor-kb-ui-RAG",
        },
        "kind": "bundled-in-tree",
        "data_dir": str(data_dir) if data_dir else None,
        "produces": {
            "source_kinds": ["application/x-fmu"],
            "region_kinds": ["fmu_variable", "fmu_parameter", "simulation_result", "plot"],
            "source_ref_kinds": ["fmu-variable", "fmu-simulation-time"],
        },
        "invocation": {
            "kind": "mcp-stdio",
            "command": "anchor-mcp",   # bundled — same MCP server hosts this extension's tools
            "args": [],
            "tools_namespace": TOOLS_NAMESPACE,
        },
        "ui_hints": {
            "node_types": [
                {"name": "fmu:model", "renders": "card with input/output handles + parameters"},
                {"name": "fmu:variable", "renders": "single-variable badge with current value"},
                {"name": "fmu:plot", "renders": "Recharts line plot of selected variables"},
            ],
            "edge_styles": {
                "fmu:wires": {"stroke": "#0EA5E9", "dasharray": "0"},
            },
            "source_ref_handlers": {
                "fmu-variable": "open the FMU model node, highlight that variable",
                "fmu-simulation-time": "open the plot node, scrub to that time",
            },
        },
    }


def build_service(
    data_dir: Path,
    bus: object,
    *,
    runtime: object | None = None,
):
    """Wire up FmuService with FS-backed storage and a real or fake runtime.

    `runtime` defaults to FakeFmuRuntime when FMPy isn't installed — keeps
    the extension working in offline/demo mode. Tests inject MemoryFmuStore +
    FakeFmuRuntime directly.
    """
    from anchor.core.ports.event_bus import EventBus
    from anchor.extensions.anchor_fmus.core.services import FmuService
    from anchor.extensions.anchor_fmus.infra.fs_store import FsFmuStore

    if runtime is None:
        try:
            from anchor.extensions.anchor_fmus.infra.fmpy_runtime import FmpyFmuRuntime
            runtime = FmpyFmuRuntime()
        except ImportError:
            from anchor.extensions.anchor_fmus.infra.fake_runtime import FakeFmuRuntime
            runtime = FakeFmuRuntime()

    return FmuService(
        store=FsFmuStore(data_dir),
        runtime=runtime,
        bus=bus,  # type: ignore[arg-type]
    )
