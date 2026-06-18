"""Single MCP server exposing canvas + bundled extensions' tool sets.

Tool dispatch routes by handler ownership: each tool name comes from one
of the per-extension `tool_definitions()` lists, and `call_tool` routes
to whichever handler claimed it. PDF tools (`ingest_pdf`, `list_documents`,
...) live in `anchor_pdfs.mcp_handlers`; FMU tools (`fmu_inspect`, ...) in
`anchor_fmus.mcp_handlers`; CAD tools (`inspect`, `list_models`, ...) in
`anchor_cad.mcp_handlers`. Canvas tools live in `handlers_canvas`.

External (third-party) OIP producers are NOT yet aggregated here — that's
the MCP-proxy work documented in OIP.md as the next major feature.
"""
from __future__ import annotations

import copy
from typing import Any

import json as _json

from mcp.server import Server
from mcp.types import ImageContent, Resource, TextContent, Tool
from pydantic import AnyUrl

from anchor.adapters.mcp import handlers_canvas
from anchor.adapters.mcp.services import ServiceBundle, fmu_tools_available
from anchor.adapters.mcp.router import ProjectRouter
from anchor.extensions.anchor_cad import mcp_handlers as cad_handlers
from anchor.extensions.anchor_fmus import mcp_handlers as fmu_handlers
from anchor.extensions.anchor_pdfs import mcp_handlers as pdf_handlers
from anchor.extensions.anchor_sysml import mcp_handlers as sysml_handlers
from anchor.infra.environment import NoEnvironmentError, NoProjectError
from anchor.adapters.status import build_status_summary


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
- This server serves one ENVIRONMENT (a named profile = the data zone). It
  holds PROJECTS; each project is a corpus (documents) plus its canvases.
- Project-scoped tools take an optional `project` argument. Omit it to use the
  default project. Use `list_projects` to see the options, `create_project` to
  make one. A missing/unknown project returns a self-correcting error.
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

Project resolution check:
- If visible data looks wrong, call `list_projects` to see this environment's
  projects, and pass the right one as the `project` argument. Call
  `anchor_status` to confirm the resolved environment and data dir.
- This server is one environment (one data zone). To use a different
  environment, the user adds a second named MCP server (`anchor-mcp --env
  <name>`). You cannot cross environments from here.
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

Status tools:
- anchor_status: show cwd, config path, data dir, and document/canvas counts

PDF tools (extension anchor_pdfs):
- ingest_pdf / list_documents / get_document_index
- search_documents — semantic search across embedded gold regions
- get_gold_regions / get_page_text / get_page_image / get_crop / get_pdf

Harness ingestion (provider = harness, no API key):
- ingest_begin / ingest_get_page / ingest_submit_page
- ingest_status (resume by slug) / ingest_finalize / ingest_abort
You (the agent) polish each page and group regions by candidate item
ids; the server validates, computes bboxes, embeds, and publishes
atomically on finalize.

FMU tools (anchor_fmus, optional): fmu_inspect / fmu_list_models / fmu_simulate / ...
CAD tools (anchor_cad): inspect / list_models / set_parameter / ...
SysML tools (anchor_sysml): sysml_render / sysml_export

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

~/.anchor/envs/<env>/projects/<project>/
  bronze/<filename>.pdf
  silver/<slug>/{index.json, pages/}
  gold/<slug>/{pages/<n>.regions.json, pages/<n>/<region-id>.png}
  canvases/<slug>/{meta.json, state.json, events.jsonl}
"""


def _error_result(exc: Exception) -> str:
    return _json.dumps({"error": str(exc)})


STATUS_TOOL_DEFINITION = {
    "name": "anchor_status",
    "description": (
        "Show ANCHOR's resolved project config, data directory, and document "
        "and canvas counts. Use this when an agent appears to be connected "
        "to the wrong project or an empty data zone."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


_PROJECT_ARG_DESC = (
    "The project (a corpus inside this environment) to act on. Omit to use the "
    "environment's default project. A named project must already exist — create "
    "it with create_project, or call list_projects to see the options."
)


LIFECYCLE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_projects",
        "description": (
            "List the projects in this Anchor environment (name + description). "
            "Use it to pick the right project before a project-scoped call."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "create_project",
        "description": (
            "Create a new project (its own documents + canvases) in this "
            "environment. Suggest a short description from the user's first "
            "documents; the user can edit it later."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "create_environment",
        "description": (
            "Create a new Anchor environment — a named profile that is the "
            "trust / egress boundary holding projects. Ask whether documents "
            "are processed on the user's machine or via an API before choosing "
            "a provider. `name` is a short identifier (e.g. 'local', 'work')."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "provider": {"type": "string"},
                "base_url": {"type": "string"},
                "embed_model": {"type": "string"},
                "description": {"type": "string"},
            },
        },
    },
    {
        "name": "update_project",
        "description": (
            "Update a project's description (peer of `anchor project "
            "set-description`). Preserves any config overrides."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name", "description"],
        },
    },
    {
        "name": "open_project",
        "description": (
            "Set the session default project so later calls may omit `project`. "
            "The project must already exist."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]


def _with_project_arg(defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Advertise an optional ``project`` on each project-scoped tool."""
    out: list[dict[str, Any]] = []
    for definition in defs:
        copied = copy.deepcopy(definition)
        schema = copied.setdefault("inputSchema", {"type": "object"})
        props = schema.setdefault("properties", {})
        props.setdefault("project", {"type": "string", "description": _PROJECT_ARG_DESC})
        out.append(copied)
    return out


def _resolution_error(exc: NoProjectError | NoEnvironmentError) -> str:
    if isinstance(exc, NoProjectError):
        return _json.dumps(
            {"error": "no_project", "message": str(exc), "available": exc.available}
        )
    return _json.dumps(
        {"error": "no_environment", "message": str(exc), "environment": exc.name}
    )


def _handle_lifecycle(router: ProjectRouter, name: str, args: dict[str, Any]) -> str:
    if name == "list_projects":
        return _json.dumps(router.list_projects())
    if name == "create_project":
        return _json.dumps(router.create_project(args["name"], args.get("description", "")))
    if name == "create_environment":
        return _json.dumps(
            router.create_environment(
                args.get("name"),
                provider=args.get("provider"),
                base_url=args.get("base_url"),
                embed_model=args.get("embed_model"),
                description=args.get("description"),
            )
        )
    if name == "update_project":
        return _json.dumps(router.update_project(args["name"], args.get("description", "")))
    if name == "open_project":
        return _json.dumps(router.open_project(args["name"]))
    raise RuntimeError(f"unknown lifecycle tool {name!r}")


def build_mcp_server(
    *,
    bundle: ServiceBundle | None = None,
    router: ProjectRouter | None = None,
    name: str = "anchor",
) -> Server:
    """Build the MCP server.

    Pass a ``router`` for the #120 multiproject model (one server, projects by
    per-call name, lifecycle tools, self-correcting resolution errors), or a
    single ``bundle`` for legacy single-project mode (no ``project`` arg, no
    lifecycle tools).
    """
    if bundle is None and router is None:
        raise ValueError("build_mcp_server requires either a bundle or a router")
    multiproject = router is not None
    app = Server(name, instructions=INSTRUCTIONS)

    def get_bundle(project: str | None) -> ServiceBundle:
        if router is not None:
            return router.bundle_for(project)
        assert bundle is not None
        return bundle

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
    fmu_present = fmu_tools_available() if multiproject else (bundle.fmu is not None)
    fmu_defs = fmu_handlers.tool_definitions() if fmu_present else []
    cad_defs = cad_handlers.TOOL_DEFINITIONS if (multiproject or bundle.cad is not None) else []
    sysml_defs = (
        sysml_handlers.tool_definitions() if (multiproject or bundle.sysml is not None) else []
    )
    status_defs = [STATUS_TOOL_DEFINITION]
    lifecycle_defs = LIFECYCLE_TOOL_DEFINITIONS if multiproject else []

    project_scoped = [
        *status_defs, *canvas_defs, *pdf_defs, *fmu_defs, *cad_defs, *sysml_defs,
    ]
    advertised = (
        [*lifecycle_defs, *_with_project_arg(project_scoped)] if multiproject else project_scoped
    )

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return [Tool(**d) for d in advertised]

    status_names = {d["name"] for d in status_defs}
    lifecycle_names = {d["name"] for d in lifecycle_defs}
    canvas_names = {d["name"] for d in canvas_defs}
    fmu_names = {d["name"] for d in fmu_defs} | getattr(fmu_handlers, "LEGACY_TOOL_NAMES", set())
    cad_names = {d["name"] for d in cad_defs}
    sysml_names = {d["name"] for d in sysml_defs} | getattr(sysml_handlers, "LEGACY_TOOL_NAMES", set())

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent | ImageContent]:
        args = dict(arguments)
        try:
            if name in lifecycle_names:
                text = _handle_lifecycle(router, name, args)  # type: ignore[arg-type]
            elif name in status_names:
                b = get_bundle(args.pop("project", None))
                summary = await build_status_summary(
                    config=b.config, workspace=b.workspace, doc_store=b.doc_store,
                )
                text = _json.dumps(summary)
            elif name in canvas_names:
                b = get_bundle(args.pop("project", None))
                text = await handlers_canvas.call_tool(b.workspace, name, args)
            elif name in fmu_names:
                b = get_bundle(args.pop("project", None))
                if b.fmu is None:
                    raise RuntimeError("FMU tools are not available in this install")
                text = await fmu_handlers.call_tool(b.fmu, name, args)
            elif name in cad_names:
                b = get_bundle(args.pop("project", None))
                if b.cad is None:
                    raise RuntimeError("CAD tools are not available")
                text = await cad_handlers.call_tool(name, args, service=b.cad)
            elif name in sysml_names:
                b = get_bundle(args.pop("project", None))
                if b.sysml is None:
                    raise RuntimeError("SysML tools are not available")
                text = await sysml_handlers.call_tool(b.sysml, name, args)
            else:
                b = get_bundle(args.pop("project", None))
                text = await pdf_handlers.call_tool(
                    b.ingest, b.doc_store, name, args,
                    synopsis=b.synopsis,
                    ingest_session=b.ingest_session,
                )
        except (NoProjectError, NoEnvironmentError) as exc:
            text = _resolution_error(exc)
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
