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

import json as _json

from mcp.server import Server
from mcp.types import ImageContent, Resource, TextContent, Tool
from pydantic import AnyUrl

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


# ── Server instructions ────────────────────────────────────────────────────
#
# The MCP protocol lets a server return a system-prompt-prepended block on
# initialize. Claude Code / Cursor / opencode prepend it to the user's
# prompt every time the server connects, so the agent picks up the
# "what Anchor is + how to use placeholders" briefing for free. Keep it
# short — agents pay for it on every turn — and load-bearing.

INSTRUCTIONS = """\
You're connected to Anchor, a knowledge-grounded engineering canvas.

What it is:
- Three substrates live on disk under ~/anchor-data: documents (ingested
  PDFs/CAD/FMUs), workspaces (canvases), and a per-session event bus.
- You have HTTP/MCP/CLI parity for every operation. Pick MCP from here.

Source-grounding (load-bearing):
- Every value placed on the canvas should carry `data.source_ref`
  pointing back at its origin (page+bbox for PDFs, region_id for
  gold-extracted regions). Spec rows carry their own per-row
  source_ref. This is the project's primary trust mechanism.
- Source refs inside node data are enough for grounding. Visual edges
  are optional wiring, not a required part of every grounded answer.

Canvas editing policy:
- Classify the user's intent before changing the canvas.
- Treat requests whose main intent is to answer, summarize, extract,
  populate, fill, revise, or update content as content-only. Use
  `canvas_update_node` on existing nodes when possible.
- Preserve existing canvas wiring by default. Do not add, remove, or
  reroute edges unless the user clearly asks for wiring changes.
- Change edges only when the user's main intent is to change wiring,
  relationships, provenance visualization, layout connections, or graph
  structure.
- If no suitable node exists, you may create a new content node with
  source_ref data. Still do not add edges unless the user asked for
  wiring or visual provenance edges.

When the user asks you to populate placeholders:
1. `canvas_list_placeholders(workspace_slug)` returns the ones flagged.
2. For each, use `search_documents` (semantic) or `get_gold_regions`
   to find the answer.
3. Replace the placeholder by writing real data via
   `canvas_update_node({id, label, data: {placeholder: false,
   source_ref: ..., rows: [...]}})`.
4. Preserve existing edges and layout unless the user's main intent is
   wiring, provenance visualization, graph structure, or reorganization.

If you're producing a snapshot of the canvas, use `canvas_snapshot(...,
format: "inline")` so the host renders the image inline.

Stuck? Read the `anchor://help` resource for the deeper tour.
"""


HELP_RESOURCE_TEXT = INSTRUCTIONS + """

── Full tool reference ────────────────────────────────────────────────────

Canvas tools:
- canvas_list_workspaces / canvas_create_workspace / canvas_get_state
- canvas_add_node / canvas_update_node / canvas_remove_node
- canvas_add_edge / canvas_update_edge / canvas_remove_edge
  (explicit wiring only; do not use for ordinary content updates)
- canvas_clear / canvas_organize_subtree / canvas_align / canvas_distribute
- canvas_create_sub_canvas — nest a child canvas inside a node
- canvas_list_placeholders — your "what to fill" entrypoint
- canvas_snapshot — PNG of the live canvas; pass format='inline'

PDF tools (extension anchor_pdfs):
- ingest_pdf / list_documents / get_document_index
- search_documents — semantic search across embedded gold regions
- get_gold_regions / get_page_text / get_page_image / get_crop / get_pdf

FMU tools (anchor_fmus, optional): fmu.inspect / fmu.list / fmu.simulate / ...
CAD tools (anchor_cad): inspect / list_models / set_parameter / ...
SysML tools (anchor_sysml): sysml.render / sysml.export

── Placeholder protocol ───────────────────────────────────────────────────

A placeholder node carries `data.placeholder == true` and optionally
`data.placeholder_hint == "<what we want here>"`. Visual: dashed
sky-blue outline + hint chip. Agent: enumerate via
`canvas_list_placeholders`, fill via `canvas_update_node({id, data: {
placeholder: false, source_ref: {slug, page, bbox, region_id?}, rows: [
{key, value, source_ref}, ... ]}})`. Keep `placeholder_hint` in `data`
even after filling. It is useful audit history. Do not add evidence
edges while filling placeholders unless the user explicitly asks for
edge wiring.

── Where data lives ───────────────────────────────────────────────────────

~/anchor-data/
  bronze/<filename>.pdf
  silver/<slug>/{index.json, pages/}
  gold/<slug>/{pages/<n>.regions.json, pages/<n>/<region-id>.png}
  canvases/<slug>/{meta.json, state.json, events.jsonl}
"""


def _error_result(exc: Exception) -> str:
    return _json.dumps({"error": str(exc)})


def build_mcp_server(
    *,
    workspace: WorkspaceService,
    ingest: IngestService,
    doc_store: DocStore,
    fmu: FmuService | None = None,
    cad: CadService | None = None,
    sysml: SysmlService | None = None,
    synopsis: Any | None = None,
    name: str = "anchor",
) -> Server:
    app = Server(name, instructions=INSTRUCTIONS)

    @app.list_resources()
    async def list_resources() -> list[Resource]:
        return [
            Resource(
                uri=AnyUrl("anchor://help"),
                name="Anchor help",
                description=(
                    "Deeper tour of Anchor's tools, placeholder protocol, "
                    "and on-disk layout. Read this when stuck."
                ),
                mimeType="text/markdown",
            ),
        ]

    @app.read_resource()
    async def read_resource(uri: AnyUrl) -> str:
        if str(uri) == "anchor://help":
            return HELP_RESOURCE_TEXT
        raise ValueError(f"unknown resource: {uri}")

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
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent | ImageContent]:
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
                text = await pdf_handlers.call_tool(
                    ingest, doc_store, name, dict(arguments),
                    synopsis=synopsis,
                )
        except Exception as exc:  # noqa: BLE001  - surface to caller as JSON
            text = _error_result(exc)
        # Promote inline-image envelopes (`{"_mcp_image_b64": ..., "_mcp_mime": ...}`)
        # to MCP ImageContent so the host harness renders the bytes inline.
        # Any other return shape stays TextContent.
        try:
            decoded = _json.loads(text)
        except (ValueError, TypeError):
            decoded = None
        if isinstance(decoded, dict) and "_mcp_image_b64" in decoded:
            return [ImageContent(
                type="image",
                data=decoded["_mcp_image_b64"],
                mimeType=decoded.get("_mcp_mime", "image/png"),
            )]
        return [TextContent(type="text", text=text)]

    return app
