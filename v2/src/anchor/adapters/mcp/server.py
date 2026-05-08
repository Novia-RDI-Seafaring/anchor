"""Single MCP server exposing canvas + bundled extensions' tool sets.

Tool dispatch routes by handler ownership: each tool name comes from one
of the per-extension `tool_definitions()` lists, and `call_tool` routes
to whichever handler claimed it. PDF tools (`ingest_pdf`, `list_documents`,
...) live in `anchor_pdfs.mcp_handlers`; FMU tools (`fmu.inspect`, ...) in
`anchor_fmus.mcp_handlers`; CAD tools (`inspect`, `list_models`, ...) in
`anchor_cad.mcp_handlers`. Canvas tools live in `handlers_canvas`.

External (third-party) OIP producers are NOT yet aggregated here — that's
the MCP-proxy work documented in OIP.md as the next major feature.
"""
from __future__ import annotations

from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from anchor.adapters.mcp import handlers_canvas
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_cad.core.services import CadService
from anchor.extensions.anchor_cad import mcp_handlers as cad_handlers
from anchor.extensions.anchor_fmus import mcp_handlers as fmu_handlers
from anchor.extensions.anchor_fmus.core.services import FmuService
from anchor.extensions.anchor_pdfs import mcp_handlers as pdf_handlers
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_sysml import mcp_handlers as sysml_handlers
from anchor.extensions.anchor_sysml.core.services import SysmlService


def build_mcp_server(
    *,
    workspace: WorkspaceService,
    ingest: IngestService,
    doc_store: DocStore,
    fmu: FmuService | None = None,
    cad: CadService | None = None,
    sysml: SysmlService | None = None,
    name: str = "anchor",
) -> Server:
    app = Server(name)

    canvas_defs = handlers_canvas.tool_definitions()
    pdf_defs = pdf_handlers.tool_definitions()
    fmu_defs = fmu_handlers.tool_definitions() if fmu is not None else []
    cad_defs = cad_handlers.TOOL_DEFINITIONS if cad is not None else []
    sysml_defs = sysml_handlers.tool_definitions() if sysml is not None else []

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [Tool(**d) for d in [*canvas_defs, *pdf_defs, *fmu_defs, *cad_defs, *sysml_defs]]

    canvas_names = {d["name"] for d in canvas_defs}
    fmu_names = {d["name"] for d in fmu_defs}
    cad_names = {d["name"] for d in cad_defs}
    sysml_names = {d["name"] for d in sysml_defs}

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            if name in canvas_names:
                text = await handlers_canvas.call_tool(workspace, name, dict(arguments))
            elif name in fmu_names and fmu is not None:
                text = await fmu_handlers.call_tool(fmu, name, dict(arguments))
            elif name in cad_names and cad is not None:
                text = await cad_handlers.call_tool(name, dict(arguments), service=cad)
            elif name in sysml_names and sysml is not None:
                text = await sysml_handlers.call_tool(sysml, name, dict(arguments))
            else:
                text = await pdf_handlers.call_tool(ingest, doc_store, name, dict(arguments))
        except Exception as exc:  # noqa: BLE001  - surface to caller as JSON
            text = f'{{"error": {exc!s}}}'
        return [TextContent(type="text", text=text)]

    return app
