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
            "homepage": "https://github.com/Novia-RDI-Seafaring/anchor",
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


class FmuRuntimeUnavailableError(RuntimeError):
    """Raised when FMPy is not installed and the caller has not opted into demo mode.

    The old behaviour silently fell back to ``FakeFmuRuntime``, which
    returned sinusoidal outputs that look like a successful simulation.
    For an engineering tool that is unsafe: a user could call
    ``simulate`` against a real-looking FMU model and trust the chart.
    We now fail closed and require an explicit demo opt-in.
    """


def build_service(
    data_dir: Path,
    bus: object,
    *,
    runtime: object | None = None,
):
    """Wire up :class:`FmuService` with FS-backed storage and a runtime.

    Resolution order for the runtime:

    1. Explicit ``runtime`` argument (tests inject ``FakeFmuRuntime``).
    2. :class:`FmpyFmuRuntime` if FMPy is importable.
    3. ``FakeFmuRuntime`` only when ``ANCHOR_FMU_DEMO=1`` is set in the
       environment. Every result it produces is stamped with
       ``synthetic=True`` so HTTP/MCP/CLI clients can render a clear
       "demo only" badge.

    If neither FMPy nor the demo opt-in is present we raise rather than
    return a silently-fake service — the previous behaviour caused exactly
    the failure mode flagged by the OSS readiness review.
    """
    import logging
    import os

    from anchor.extensions.anchor_fmus.core.services import FmuService
    from anchor.extensions.anchor_fmus.infra.fs_store import FsFmuStore

    if runtime is None:
        try:
            from anchor.extensions.anchor_fmus.infra.fmpy_runtime import FmpyFmuRuntime
            runtime = FmpyFmuRuntime()
        except ImportError as exc:
            if os.environ.get("ANCHOR_FMU_DEMO") != "1":
                raise FmuRuntimeUnavailableError(
                    "FMPy is not installed and ANCHOR_FMU_DEMO is not set. "
                    "Install the real runtime with `uv pip install 'anchor[fmus]'` "
                    "(or `pip install fmpy>=0.3.22`). To run the synthetic "
                    "offline demo instead, set ANCHOR_FMU_DEMO=1 — all results "
                    "will be marked synthetic=true."
                ) from exc
            from anchor.extensions.anchor_fmus.infra.fake_runtime import FakeFmuRuntime
            logging.getLogger(__name__).warning(
                "FMU extension running in DEMO mode (ANCHOR_FMU_DEMO=1). "
                "Every simulation result is synthetic — do NOT trust the "
                "numbers for engineering decisions."
            )
            runtime = FakeFmuRuntime()

    return FmuService(
        store=FsFmuStore(data_dir),
        runtime=runtime,
        bus=bus,  # type: ignore[arg-type]
    )
