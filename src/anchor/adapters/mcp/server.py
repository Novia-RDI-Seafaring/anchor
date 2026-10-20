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
import json as _json
import time
from pathlib import Path
from typing import Any

import jsonschema
from mcp.server import Server, ServerRequestContext
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ImageContent,
    ListResourcesResult,
    ListToolsResult,
    PaginatedRequestParams,
    ReadResourceRequestParams,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)

from anchor.adapters.mcp import handlers_canvas, handlers_extensions, handlers_intents, tiering
from anchor.adapters.mcp.router import ProjectRouter
from anchor.adapters.mcp.server_instructions import HELP_RESOURCE_TEXT, INSTRUCTIONS
from anchor.adapters.mcp.services import active_extensions_for_bundle, fmu_tools_available
from anchor.adapters.project_runtime import ProjectRuntime
from anchor.adapters.status import build_status_summary
from anchor.core.events.actor import Actor
from anchor.extensions.anchor_cad import mcp_handlers as cad_handlers
from anchor.extensions.anchor_fmus import mcp_handlers as fmu_handlers
from anchor.extensions.anchor_pdfs import mcp_handlers as pdf_handlers
from anchor.extensions.anchor_sysml import mcp_handlers as sysml_handlers
from anchor.infra.activity import ActivityLog
from anchor.infra.environment import (
    NoEnvironmentError,
    NoProjectError,
    ProjectNotEmptyError,
)


def _error_result(exc: Exception) -> str:
    from anchor.infra.egress_policy import MissingModelCredentialError

    if isinstance(exc, MissingModelCredentialError):
        return _json.dumps(exc.to_dict())
    return _json.dumps({"error": str(exc)})


def _build_server_info(data_dir: Any) -> dict[str, Any]:
    """Resolve which env/project this server is for + any serve bound to it.

    Names the resolved env + project + data dir, then looks up a running
    ``anchor serve`` actually bound to that data dir (anchor#177, anchor#179).
    When one is up, ``serve`` carries its real base URL + canvas URL prefix so
    the agent can hand the user a URL that resolves to THIS project rather than
    guessing ``:8002``.
    """
    from pathlib import Path

    from anchor.infra.environment import identify_data_dir
    from anchor.infra.serve_registry import find_serve_for_data_dir

    env_name, project_name = identify_data_dir(data_dir)
    record = find_serve_for_data_dir(data_dir)
    serve: dict[str, Any] | None = None
    if record is not None:
        base = record.base_url()
        serve = {
            "running": True,
            "host": record.host,
            "port": record.port,
            "base_url": base,
            "canvas_url_prefix": f"{base}/c/",
            "pid": record.pid,
            "started_at": record.started_at,
        }
    return {
        "env": env_name,
        "project": project_name,
        "data_dir": str(Path(data_dir)),
        "serve": serve if serve is not None else {"running": False},
    }


CANVAS_URL_TOOL_DEFINITION = {
    "name": "canvas_url",
    "description": (
        "The address of Anchor's web app for this project, or of one canvas in "
        "it. Call this when the user asks to see, open or show Anchor, the "
        "canvas or the UI. Open the returned url in your in-app browser if you "
        "have one, else give it to the user. Never redraw a canvas as a "
        "picture or artifact of your own: it would not be the canvas."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "workspace_slug": {
                "type": "string",
                "description": "A canvas to open. Omit for the project's start page.",
            },
        },
        "additionalProperties": False,
    },
}


#: Said in the result, where it is acted on: agents read "localhost" as out
#: of their reach and handed the link back, though the app's browser pane
#: runs on this same machine, sometimes behind a tool loaded on demand.
OPEN_NEXT = (
    "Open this url now in the app's browser pane. It runs on this machine, so "
    "a localhost address loads there; if your browser tool is not loaded yet, "
    "load it first. Only when you have no browser at all, give the url to the "
    "user."
)


def _build_canvas_url(data_dir: Any, workspace_slug: str | None) -> dict[str, Any]:
    """Where the user sees this project, from the serve bound to it."""
    from anchor.core.ids import validate_workspace_slug

    info = _build_server_info(data_dir)
    serve = info["serve"]
    if workspace_slug:
        validate_workspace_slug(workspace_slug)
    if not serve.get("running"):
        return {
            "env": info["env"],
            "project": info["project"],
            "running": False,
            "start": f"anchor serve --env {info['env']} --project {info['project']}",
            "hint": (
                "No Anchor server shows this project yet. Start it with the "
                "`start` command (it runs until stopped), then call canvas_url again."
            ),
        }
    path = f"c/{workspace_slug}" if workspace_slug else ""
    return {
        "env": info["env"],
        "project": info["project"],
        "running": True,
        "url": f"{serve['base_url']}/{path}",
        "next": OPEN_NEXT,
    }


def _canvas_in_view(data_dir: Any) -> str | None:
    """The one canvas a person has open in a browser, or ``None``."""
    from anchor.infra.presence import fetch_viewing

    viewing = fetch_viewing(Path(data_dir))
    return viewing[0] if len(viewing) == 1 else None


async def _scoped_inbox(intents: Any, canvas: str, text: str) -> str:
    """Say which canvas an unnamed inbox read was scoped to, and what is elsewhere."""
    scoped = _json.loads(text)
    if not isinstance(scoped, dict) or not isinstance(scoped.get("intents"), list):
        return text
    here = {i.get("id") for i in scoped["intents"] if isinstance(i, dict)}
    # No reader: counting the others must not mark them read.
    elsewhere: dict[str, int] = {}
    for intent in await intents.list_pending():
        if intent.id not in here:
            where = intent.origin_canvas_id or intent.target or "(no canvas)"
            elsewhere[where] = elsewhere.get(where, 0) + 1
    return _json.dumps({
        **scoped,
        "canvas": canvas,
        "why": "No canvas was named, so this is the canvas open in the browser. "
        "Pass `canvas` for another one.",
        "elsewhere": elsewhere,
    })


def _served_projects(env_name: str) -> list[dict[str, Any]]:
    """Projects of ``env_name`` that a running ``anchor serve`` shows now."""
    from anchor.infra.serve_registry import list_serves

    out: list[dict[str, Any]] = []
    for record in list_serves():
        project = record.project
        if record.env == env_name and project and all(p["project"] != project for p in out):
            out.append({"project": project, "url": f"{record.base_url()}/"})
    return out


def _canvas_url_unnamed(router: Any, workspace_slug: str | None) -> dict[str, Any] | None:
    """``canvas_url`` with no project named and none opened this session.

    The user asking to see Anchor means the project on screen, not the
    environment's default. When exactly one project of this environment is
    being served, that is the one: open it for the session and return it.
    When several are, the user has to say which. ``None`` falls back to the
    default project.
    """
    served = _served_projects(router.environment().name)
    if len(served) == 1:
        router.open_project(served[0]["project"])
        return {"session_default": served[0]["project"]}
    if len(served) > 1:
        return {
            "running": True,
            "choose": served,
            "hint": "Several projects are being served. Ask the user which one, "
            "then call canvas_url with that project.",
        }
    return None


DELETE_DOCUMENT_TOOL_DEFINITION = {
    "name": "delete_document",
    "description": (
        "Delete a document and everything stored for it (original, pages, "
        "regions, crops, embeddings) from the project. Destructive and not "
        "undoable: only when the user asked, and confirm with them first. "
        "When canvases cite the document it is not deleted: the answer lists "
        "them under `cited_by`. Tell the user; with their go-ahead pass "
        "`force` to delete anyway (their cards and rows stay, with source "
        "links that point nowhere)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "The document's slug."},
            "force": {"type": "boolean", "description": "Delete even when canvases cite it."},
        },
        "required": ["slug"],
        "additionalProperties": False,
    },
    "annotations": {"destructiveHint": True, "idempotentHint": False},
}


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


SERVER_INFO_TOOL_DEFINITION = {
    "name": "server_info",
    "description": (
        "Report which env + project THIS MCP server resolves to, its data dir, "
        "and whether a running `anchor serve` is bound to that same project -- "
        "with that server's real base URL and canvas URL prefix. Use it to "
        "confirm a localhost:PORT canvas URL points at this project before "
        "you hand it to the user, instead of assuming :8002."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
}


_PROJECT_ARG_DESC = (
    "The project (a corpus inside this environment) to act on. Omit to use the "
    "session's project (set by create_project(folder=...) or open_project), "
    "else the environment's default project. A named project must already exist — create "
    "it with create_project, or call list_projects to see the options."
)


LIFECYCLE_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_projects",
        "description": (
            "List the projects in this Anchor environment (name, description, "
            "folder). Use it to pick the right project before a project-scoped call."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "create_project",
        "description": (
            "Create a new project (its own documents + canvases) in this "
            "environment. Suggest a short description from the user's first "
            "documents; the user can edit it later. Pass `folder` (the absolute "
            "path you are working in) to get the project for that folder: the "
            "one already there, or a new one named after it. It then becomes "
            "this session's default project."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "folder": {
                    "type": "string",
                    "description": "Absolute path of your working folder.",
                },
            },
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
    {
        "name": "remove_project",
        "description": (
            "Remove a project from this environment (peer of `anchor project "
            "remove`). Deregisters it; with `delete_data` also deletes its "
            "on-disk .anchor_data/ + anchor.toml. Refuses a project that still "
            "has documents/canvases unless `force` is true. Never touches "
            "other projects. Use this to undo a throwaway project."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "delete_data": {"type": "boolean"},
                "force": {"type": "boolean"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "rename_project",
        "description": (
            "Rename a project (peer of `anchor project rename`). Updates the "
            "registry + the project's anchor.toml; the folder path is "
            "unchanged. Fails if the new name already exists."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "old": {"type": "string"},
                "new": {"type": "string"},
            },
            "required": ["old", "new"],
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


def _env_file(config) -> str | None:
    """The key file of the environment that owns ``config``, for remedies."""
    from anchor.infra.egress_policy import environment_dotenv_path

    path = environment_dotenv_path(config)
    return str(path) if path is not None else None


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
        return _json.dumps(router.create_project(
            args.get("name"), args.get("description", ""), folder=args.get("folder"),
        ))
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
    if name == "remove_project":
        return _json.dumps(
            router.remove_project(
                args["name"],
                delete_data=bool(args.get("delete_data", False)),
                force=bool(args.get("force", False)),
            )
        )
    if name == "rename_project":
        return _json.dumps(router.rename_project(args["old"], args["new"]))
    raise RuntimeError(f"unknown lifecycle tool {name!r}")


def _env_identity(router: ProjectRouter) -> str:
    """A short header announcing which environment this server serves.

    Prepended to the MCP instructions so the agent knows, on connect, the
    environment name, its data zone, and what it is for. This is also how the
    agent routes correctly when several environments are wired as separate
    named servers.
    """
    from anchor.infra.environment import (
        DEFAULT_PROJECT,
        environment_meta,
        resolve_project_config,
    )
    from anchor.infra.providers import get_provider

    try:
        env = router.environment()
    except Exception:  # noqa: BLE001 — never let the header break startup
        return ""
    lines = [f"Active environment: '{env.name}'."]
    if env.initialized:
        cfg = resolve_project_config(env, DEFAULT_PROJECT)
        prov = get_provider(cfg.provider or "local")
        if prov:
            lines.append(f"- Data zone: {prov.zone} (where this environment's documents may go).")
        desc = environment_meta(env).description
        if desc:
            lines.append(f"- About: {desc}")
    else:
        lines.append("- Not set up yet. Create it with create_environment before ingesting.")
    lines.append(
        "- This server serves ONLY this environment. It holds projects (corpuses); "
        "name one with the per-call `project` argument, or call list_projects. You "
        "cannot reach another environment from here."
    )
    return "\n".join(lines) + "\n\n"


def build_mcp_server(
    *,
    bundle: ProjectRuntime | None = None,
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
    instructions = (_env_identity(router) + INSTRUCTIONS) if multiproject else INSTRUCTIONS

    def get_bundle(project: str | None) -> ProjectRuntime:
        if router is not None:
            return router.bundle_for(project)
        assert bundle is not None
        return bundle

    def _client_actor(ctx: ServerRequestContext) -> Actor:
        """Actor for canvas writes over MCP (#322): always an agent, labeled
        with the connected client's self-declared name (``clientInfo.name``
        from the initialize handshake) when the session exposes it."""
        label = "mcp-agent"
        try:
            params = ctx.session.client_params
            client_info = getattr(params, "client_info", None)
            client_name = getattr(client_info, "name", None)
            if client_name:
                label = str(client_name)
        except Exception:  # noqa: BLE001 -- attribution must never break a call
            pass
        return Actor(kind="agent", label=label)

    async def list_resources(
        ctx: ServerRequestContext, params: PaginatedRequestParams | None,
    ) -> ListResourcesResult:
        return ListResourcesResult(resources=[
            Resource(
                uri="anchor://help",
                name="Anchor help",
                description=(
                    "Deeper tour of Anchor's tools, placeholder protocol, "
                    "and on-disk layout. Read this when stuck."
                ),
                mime_type="text/markdown",
            ),
        ])

    async def read_resource(
        ctx: ServerRequestContext, params: ReadResourceRequestParams,
    ) -> ReadResourceResult:
        if params.uri == "anchor://help":
            return ReadResourceResult(contents=[TextResourceContents(
                uri=params.uri, mime_type="text/markdown", text=HELP_RESOURCE_TEXT,
            )])
        raise ValueError(f"unknown resource: {params.uri}")

    canvas_defs = handlers_canvas.tool_definitions()
    intent_defs = handlers_intents.tool_definitions()
    pdf_defs = pdf_handlers.tool_definitions()
    fmu_present = fmu_tools_available() if multiproject else (bundle.fmu is not None)
    fmu_defs = fmu_handlers.tool_definitions() if fmu_present else []
    cad_defs = cad_handlers.TOOL_DEFINITIONS if (multiproject or bundle.cad is not None) else []
    sysml_defs = (
        sysml_handlers.tool_definitions() if (multiproject or bundle.sysml is not None) else []
    )
    status_defs = [
        STATUS_TOOL_DEFINITION,
        SERVER_INFO_TOOL_DEFINITION,
        CANVAS_URL_TOOL_DEFINITION,
        DELETE_DOCUMENT_TOOL_DEFINITION,
        handlers_extensions.TOOL_DEFINITION,
    ]
    lifecycle_defs = LIFECYCLE_TOOL_DEFINITIONS if multiproject else []

    project_scoped = [
        *status_defs, *canvas_defs, *intent_defs, *pdf_defs,
        *fmu_defs, *cad_defs, *sysml_defs,
    ]
    # The full dispatchable surface, in canonical order. ``all_defs`` is what
    # every tool COULD be advertised; the tiered selector (anchor#133) picks
    # the subset advertised by default. Dispatch in ``call_tool`` routes by
    # name against this full surface regardless of advertisement, so a gated
    # tool stays callable the moment a harness discovers it.
    capabilities_def = tiering.CAPABILITIES_TOOL_DEFINITION
    # The capabilities meta-tool is project-scoped: it reports which extensions
    # are active for the resolved project, so it flows through the same
    # ``project``-arg injection as the other project-scoped tools.
    project_scoped = [capabilities_def, *project_scoped]
    if multiproject:
        all_defs = [*lifecycle_defs, *_with_project_arg(project_scoped)]
    else:
        all_defs = list(project_scoped)

    # Extension tool-name groups, used both to auto-advertise an active
    # extension and to answer the capabilities meta-tool.
    extension_names = {
        "fmu": {d["name"] for d in fmu_defs},
        "cad": {d["name"] for d in cad_defs},
        "sysml": {d["name"] for d in sysml_defs},
    }

    async def _active_extensions() -> set[str]:
        """Extensions with data in the resolved default project (best-effort).

        ``list_tools`` is connection-level (no per-call project), so we gate
        against the default/session-default project -- the one the agent is
        most likely acting on. Any resolution failure (e.g. an un-initialized
        environment) yields no active extensions; the long tail is still one
        ``anchor_list_capabilities`` call away.
        """
        try:
            b = get_bundle(None)
        except Exception:  # noqa: BLE001 -- never let list_tools fail
            return set()
        return await active_extensions_for_bundle(b)

    async def list_tools(
        ctx: ServerRequestContext, params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        active = await _active_extensions()
        advertised = tiering.select_advertised(
            all_defs, active_extensions=active, extension_names=extension_names,
        )
        return ListToolsResult(tools=[Tool(**d) for d in advertised])

    status_names = {d["name"] for d in status_defs}
    lifecycle_names = {d["name"] for d in lifecycle_defs}
    canvas_names = {d["name"] for d in canvas_defs}
    intent_names = {d["name"] for d in intent_defs}
    fmu_names = {d["name"] for d in fmu_defs} | getattr(fmu_handlers, "LEGACY_TOOL_NAMES", set())
    cad_names = {d["name"] for d in cad_defs}
    sysml_names = {d["name"] for d in sysml_defs} | getattr(sysml_handlers, "LEGACY_TOOL_NAMES", set())

    # Advertising is tiered, but every callable tool needs the same input guard.
    tool_schemas = {d["name"]: d["inputSchema"] for d in all_defs}
    for alias, canonical in {
        **fmu_handlers.LEGACY_TOOL_ALIASES, **sysml_handlers.LEGACY_TOOL_ALIASES,
    }.items():
        if canonical in tool_schemas:
            tool_schemas[alias] = tool_schemas[canonical]

    async def call_tool(
        ctx: ServerRequestContext, params: CallToolRequestParams,
    ) -> CallToolResult:
        name = params.name
        arguments = params.arguments or {}
        schema = tool_schemas.get(name)
        if schema is not None:
            try:
                jsonschema.validate(instance=arguments, schema=schema)
            except jsonschema.ValidationError as exc:
                # SDK v1 rejected invalid arguments before our handler ran.
                return CallToolResult(
                    is_error=True,
                    content=[TextContent(type="text", text=f"Input validation error: {exc.message}")],
                )
        args = dict(arguments)
        # The activity log counts the call whatever happens to it: an agent's
        # cost is in calls, and a failed one cost a turn too. The project is
        # read before the handlers pop it from the arguments.
        started = time.perf_counter()
        log_dir = None
        try:
            log_dir = Path(router.bundle_for(args.get("project")).config.data_dir)
        except Exception:  # noqa: BLE001 -- no project resolves, no log
            log_dir = None
        try:
            if name == tiering.CAPABILITIES_TOOL_NAME:
                try:
                    b = get_bundle(args.pop("project", None))
                    active = await active_extensions_for_bundle(b)
                except (NoProjectError, NoEnvironmentError):
                    raise
                except Exception:  # noqa: BLE001 -- still list the catalog
                    active = set()
                text = _json.dumps(
                    tiering.build_capabilities_payload(all_defs, active_extensions=active)
                )
            elif name in lifecycle_names:
                text = _handle_lifecycle(router, name, args)  # type: ignore[arg-type]
            elif name == SERVER_INFO_TOOL_DEFINITION["name"]:
                b = get_bundle(args.pop("project", None))
                text = _json.dumps(_build_server_info(b.config.data_dir))
            elif name == DELETE_DOCUMENT_TOOL_DEFINITION["name"]:
                from anchor.adapters.document_delete import delete_document
                from anchor.extensions.anchor_pdfs.core.ports.doc_store import IngestLockHeld

                b = get_bundle(args.pop("project", None))
                try:
                    text = _json.dumps(await delete_document(
                        b.workspace, b.doc_store, args["slug"], force=bool(args.get("force")),
                    ))
                except KeyError:
                    text = _json.dumps({"error": "not_found", "slug": args["slug"]})
                except IngestLockHeld:
                    text = _json.dumps({"error": "ingesting", "slug": args["slug"],
                                        "next": "Delete it when the ingest finishes."})
            elif name == CANVAS_URL_TOOL_DEFINITION["name"]:
                project = args.pop("project", None)
                slug = args.get("workspace_slug")
                picked = (
                    _canvas_url_unnamed(router, slug)
                    if router is not None and project is None and router.session_default is None
                    else None
                )
                if picked is not None and "choose" in picked:
                    text = _json.dumps(picked)
                else:
                    b = get_bundle(picked["session_default"] if picked else project)
                    text = _json.dumps(_build_canvas_url(b.config.data_dir, slug))
            elif name == handlers_extensions.TOOL_NAME:
                b = get_bundle(args.pop("project", None))
                text = handlers_extensions.call_tool(
                    b.extension_status, b.config.data_dir
                )
            elif name in status_names:
                b = get_bundle(args.pop("project", None))
                summary = await build_status_summary(
                    config=b.config, workspace=b.workspace, doc_store=b.doc_store,
                )
                text = _json.dumps(summary)
            elif name in canvas_names:
                b = get_bundle(args.pop("project", None))

                text = await handlers_canvas.call_tool(
                    b.workspace, name, args,
                    actor=_client_actor(ctx), data_dir=Path(b.config.data_dir),
                )
                if name == "canvas_create_workspace":
                    # A new canvas is made to be looked at: hand back where.
                    made = _json.loads(text)
                    if isinstance(made, dict) and "error" not in made:
                        where = _build_canvas_url(b.config.data_dir, args.get("slug"))
                        made.update({k: where[k] for k in ("url", "next", "start", "hint") if k in where})
                        text = _json.dumps(made)
            elif name in intent_names:
                b = get_bundle(args.pop("project", None))
                if b.intents is None:
                    raise RuntimeError("intent queue is not available")
                inferred = None
                if name in ("list_pending_intents", "intents_wait") and not args.get("canvas"):
                    inferred = _canvas_in_view(b.config.data_dir)
                    if inferred:
                        args = {**args, "canvas": inferred}
                text = await handlers_intents.call_tool(
                    b.intents, name, args, actor=_client_actor(ctx),
                    activity=ActivityLog(Path(b.config.data_dir)),
                )
                if inferred and name == "list_pending_intents":
                    text = await _scoped_inbox(b.intents, inferred, text)
                elif inferred:
                    text = _json.dumps({**_json.loads(text), "canvas": inferred})
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
                    env_file=_env_file(b.config),
                )
        except (NoProjectError, NoEnvironmentError) as exc:
            text = _resolution_error(exc)
        except ProjectNotEmptyError as exc:
            text = _json.dumps(
                {
                    "error": "project_not_empty",
                    "message": str(exc),
                    "project": exc.name,
                    "documents": exc.documents,
                    "canvases": exc.canvases,
                }
            )
        except Exception as exc:  # noqa: BLE001  - surface to caller as JSON
            text = _error_result(exc)
        if log_dir is not None:
            ActivityLog(log_dir).record(
                kind="mcp",
                name=name,
                ms=round((time.perf_counter() - started) * 1000, 1),
                intent=arguments.get("id") if name.startswith("intent_") or name == "resolve_intent" else None,
            )
        # Promote inline-image envelopes (`{"_mcp_image_b64": ..., "_mcp_mime": ...}`)
        # to MCP ImageContent so the host harness renders the bytes inline.
        # Any other return shape stays TextContent.
        try:
            decoded = _json.loads(text)
        except (ValueError, TypeError):
            decoded = None
        if isinstance(decoded, dict) and "_mcp_image_b64" in decoded:
            return CallToolResult(content=[ImageContent(
                type="image",
                data=decoded["_mcp_image_b64"],
                mime_type=decoded.get("_mcp_mime", "image/png"),
            )])
        return CallToolResult(content=[TextContent(type="text", text=text)])

    from anchor import __version__

    return Server(
        name=name, version=__version__, instructions=instructions,
        on_list_resources=list_resources, on_read_resource=read_resource,
        on_list_tools=list_tools, on_call_tool=call_tool,
    )
