"""Single MCP server exposing canvas + bundled extensions' tool sets.

Tool dispatch routes by namespace prefix (e.g. tools starting with `fmu.`
go to the FMU extension; tools starting with `canvas_` go to the canvas
service; legacy unprefixed ingest tools go to the PDF extension's
handlers).

External (third-party) OIP producers are NOT yet aggregated here — that's
the MCP-proxy work documented in OIP.md as the next major feature.
"""
from __future__ import annotations

from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from anchor.adapters.mcp import handlers_canvas, handlers_ingest
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_fmus import mcp_handlers as fmu_handlers
from anchor.extensions.anchor_fmus.core.services import FmuService


def build_mcp_server(
    *,
    workspace: WorkspaceService,
    ingest: IngestService,
    doc_store: DocStore,
    fmu: FmuService | None = None,
    name: str = "anchor",
) -> Server:
    app = Server(name)

    canvas_defs = handlers_canvas.tool_definitions()
    ingest_defs = handlers_ingest.tool_definitions()
    fmu_defs = fmu_handlers.tool_definitions() if fmu is not None else []

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [Tool(**d) for d in [*canvas_defs, *ingest_defs, *fmu_defs]]

    canvas_names = {d["name"] for d in canvas_defs}
    fmu_names = {d["name"] for d in fmu_defs}

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            if name in canvas_names:
                text = await handlers_canvas.call_tool(workspace, name, dict(arguments))
            elif name in fmu_names and fmu is not None:
                text = await fmu_handlers.call_tool(fmu, name, dict(arguments))
            else:
                text = await handlers_ingest.call_tool(ingest, doc_store, name, dict(arguments))
        except Exception as exc:  # noqa: BLE001  - surface to caller as JSON
            text = f'{{"error": {exc!s}}}'
        return [TextContent(type="text", text=text)]

    return app
