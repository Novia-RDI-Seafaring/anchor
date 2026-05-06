"""Shared MCP handler definitions for the canvas.

A single source of truth for tools and resources, parameterised over a
`CanvasOps` protocol so the same handlers can be driven by either:

  * `InProcessOps`  — calls into a local `Canvas` instance (when MCP is
    mounted inside the FastAPI canvas server)
  * `HttpOps`       — talks to a remote canvas server's REST API (when
    running the legacy stdio shim, `anchor-canvas-mcp`)

Both transports therefore expose identical tool/resource catalogues.

Composite tools encode the design rules from CLAUDE.md (one table per
extraction; row-level provenance on spec rows; documents linked to model
nodes, model nodes linked to FMUs) so an agent that uses them can't
violate the rules by accident.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol

import httpx
from mcp.server import Server
from mcp.server.session import ServerSession
from mcp.types import (
    AnyUrl,
    Resource,
    TextContent,
    Tool,
)
from pydantic import AnyUrl as PydAnyUrl

logger = logging.getLogger(__name__)


# --- Ops protocol ---------------------------------------------------------


class CanvasOps(Protocol):
    """Backend interface used by the MCP handlers."""

    async def get_state(self) -> dict: ...
    async def add_node(self, **kwargs: Any) -> dict: ...
    async def update_node(self, node_id: str, **kwargs: Any) -> dict | None: ...
    async def remove_node(self, node_id: str) -> dict: ...
    async def add_edge(self, **kwargs: Any) -> dict | None: ...
    async def remove_edge(self, edge_id: str) -> dict: ...
    async def clear(self) -> dict: ...
    async def add_nodes_bulk(self, items: list[dict]) -> list[dict]: ...
    async def add_edges_bulk(self, items: list[dict]) -> list[dict | None]: ...
    async def list_documents(self) -> list[dict]: ...
    async def get_document_index(self, slug: str) -> dict: ...


class InProcessOps:
    """Drive operations directly against a `Canvas` instance and FastAPI app state.

    Used when MCP is mounted inside the same process as the canvas server.
    `data_dir` mirrors the `_data_dir` global in `server.py`; passed in to
    avoid an import cycle.
    """

    def __init__(self, canvas, data_dir):
        self._canvas = canvas
        self._data_dir = data_dir

    async def get_state(self) -> dict:
        return self._canvas.get_state()

    async def add_node(self, **kwargs: Any) -> dict:
        return self._canvas.add_node(**kwargs).model_dump()

    async def update_node(self, node_id: str, **kwargs: Any) -> dict | None:
        node = self._canvas.update_node(node_id, **kwargs)
        return node.model_dump() if node else None

    async def remove_node(self, node_id: str) -> dict:
        return {"removed": self._canvas.remove_node(node_id)}

    async def add_edge(self, **kwargs: Any) -> dict | None:
        edge = self._canvas.add_edge(**kwargs)
        return edge.model_dump() if edge else None

    async def remove_edge(self, edge_id: str) -> dict:
        return {"removed": self._canvas.remove_edge(edge_id)}

    async def clear(self) -> dict:
        self._canvas.clear()
        return {"cleared": True}

    async def add_nodes_bulk(self, items: list[dict]) -> list[dict]:
        return [self._canvas.add_node(**i).model_dump() for i in items]

    async def add_edges_bulk(self, items: list[dict]) -> list[dict | None]:
        out: list[dict | None] = []
        for i in items:
            edge = self._canvas.add_edge(**i)
            out.append(edge.model_dump() if edge else None)
        return out

    async def list_documents(self) -> list[dict]:
        if not self._data_dir:
            return []
        silver = self._data_dir / "silver"
        if not silver.is_dir():
            return []
        docs: list[dict] = []
        for d in sorted(silver.iterdir()):
            if not d.is_dir():
                continue
            slug = d.name
            info = {"slug": slug, "title": slug, "pages": 0, "has_gold": False}
            index_path = d / "index.json"
            if index_path.exists():
                idx = json.loads(index_path.read_text())
                info["title"] = idx.get("document", {}).get("title", slug)
                info["pages"] = idx.get("document", {}).get("page_count", 0)
            info["has_gold"] = (self._data_dir / "gold" / slug / "pages").is_dir()
            docs.append(info)
        return docs

    async def get_document_index(self, slug: str) -> dict:
        if not self._data_dir:
            return {"error": "No data directory configured"}
        index_path = self._data_dir / "silver" / slug / "index.json"
        if not index_path.exists():
            return {"error": f"No index for '{slug}'"}
        return json.loads(index_path.read_text())


class HttpOps:
    """Drive operations against a remote canvas server's REST API.

    Used by the stdio shim (`anchor-canvas-mcp`) so existing Claude Code
    `mcp.json` configs keep working unchanged.
    """

    def __init__(self, base_url: str):
        self._base_url = base_url

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url, timeout=10)

    async def get_state(self) -> dict:
        async with await self._client() as c:
            return (await c.get("/api/state")).json()

    async def add_node(self, **kwargs: Any) -> dict:
        async with await self._client() as c:
            return (await c.post("/api/nodes", json=kwargs)).json()

    async def update_node(self, node_id: str, **kwargs: Any) -> dict | None:
        async with await self._client() as c:
            return (await c.patch(f"/api/nodes/{node_id}", json=kwargs)).json()

    async def remove_node(self, node_id: str) -> dict:
        async with await self._client() as c:
            return (await c.delete(f"/api/nodes/{node_id}")).json()

    async def add_edge(self, **kwargs: Any) -> dict | None:
        async with await self._client() as c:
            return (await c.post("/api/edges", json=kwargs)).json()

    async def remove_edge(self, edge_id: str) -> dict:
        async with await self._client() as c:
            return (await c.delete(f"/api/edges/{edge_id}")).json()

    async def clear(self) -> dict:
        async with await self._client() as c:
            return (await c.post("/api/clear")).json()

    async def add_nodes_bulk(self, items: list[dict]) -> list[dict]:
        async with await self._client() as c:
            return (await c.post("/api/nodes/bulk", json=items)).json()

    async def add_edges_bulk(self, items: list[dict]) -> list[dict | None]:
        async with await self._client() as c:
            return (await c.post("/api/edges/bulk", json=items)).json()

    async def list_documents(self) -> list[dict]:
        async with await self._client() as c:
            return (await c.get("/api/documents")).json()

    async def get_document_index(self, slug: str) -> dict:
        async with await self._client() as c:
            return (await c.get(f"/api/documents/{slug}/index")).json()


# --- Session registry -----------------------------------------------------


class SessionRegistry:
    """Tracks active MCP sessions so we can broadcast resource notifications.

    Sessions register themselves the first time a handler runs against them
    (via `track_session`). On send failure (closed stream) they're dropped.
    """

    def __init__(self) -> None:
        self._sessions: set[ServerSession] = set()

    def track(self, session: ServerSession | None) -> None:
        if session is not None:
            self._sessions.add(session)

    async def broadcast_resource_updated(self, uri: str) -> None:
        dead: list[ServerSession] = []
        for s in list(self._sessions):
            try:
                await s.send_resource_updated(PydAnyUrl(uri))
            except Exception as exc:
                logger.debug("dropping dead MCP session: %s", exc)
                dead.append(s)
        for s in dead:
            self._sessions.discard(s)


# --- Tool & resource catalogue --------------------------------------------


def _tools() -> list[Tool]:
    return [
        # --- Composites (the "do the right thing" entry points) ---
        Tool(
            name="canvas_attach_document",
            description=(
                "Attach an ingested document to the canvas. Reads the silver index for "
                "the given slug and creates a `document` node carrying the title and "
                "page count. Returns the created node."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {"type": "string", "description": "Document slug (as listed by canvas_get_documents)"},
                    "x": {"type": "number", "default": 0},
                    "y": {"type": "number", "default": 0},
                },
                "required": ["slug"],
            },
        ),
        Tool(
            name="canvas_place_grounded_table",
            description=(
                "Place a grounded spec table on the canvas with row-level provenance. "
                "Creates one `spec` node and, for each row that carries a `source`, "
                "an anchored evidence edge from that row to the document node. "
                "Encodes the design rule: one table per extraction, source per row."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "doc_node_id": {"type": "string", "description": "ID of the document node to anchor sources to"},
                    "title": {"type": "string", "description": "Title for the spec table"},
                    "rows": {
                        "type": "array",
                        "description": "Spec rows. Each row should carry a `source` referencing a page/bbox in the document.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "parameter": {"type": "string"},
                                "value": {"type": "string"},
                                "unit": {"type": "string"},
                                "source": {
                                    "type": "object",
                                    "properties": {
                                        "doc_id": {"type": "string"},
                                        "filename": {"type": "string"},
                                        "page": {"type": "integer"},
                                        "bbox": {"type": "array", "items": {"type": "number"}},
                                    },
                                },
                            },
                            "required": ["parameter", "value"],
                        },
                    },
                    "x": {"type": "number", "default": 320},
                    "y": {"type": "number", "default": 0},
                },
                "required": ["doc_node_id", "title", "rows"],
            },
        ),
        Tool(
            name="canvas_link_model",
            description=(
                "Connect a model node to a target (typically a document or an FMU). "
                "Use to wire doc→model (model's source documents) or model→fmu "
                "(model parameters feeding into a simulation)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "model_node_id": {"type": "string"},
                    "target_id": {"type": "string"},
                    "label": {"type": "string", "default": ""},
                },
                "required": ["model_node_id", "target_id"],
            },
        ),
        Tool(
            name="canvas_get_documents",
            description="List ingested documents available to attach to the canvas (slug, title, pages, has_gold).",
            inputSchema={"type": "object", "properties": {}},
        ),
        # --- Primitives ---
        Tool(
            name="canvas_add_node",
            description=(
                "Add a node to the canvas. Types: concept, entity, fact, document, "
                "spec, image, area, model, fmu, plot, funnel."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "node_type": {"type": "string", "default": "concept"},
                    "label": {"type": "string"},
                    "x": {"type": "number", "default": 0},
                    "y": {"type": "number", "default": 0},
                    "parent": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["label"],
            },
        ),
        Tool(
            name="canvas_update_node",
            description="Update an existing node's properties (label, position, data).",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "data": {"type": "object"},
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="canvas_remove_node",
            description="Remove a node and its connected edges from the canvas.",
            inputSchema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        ),
        Tool(
            name="canvas_add_edge",
            description="Connect two nodes with an edge.",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "label": {"type": "string", "default": ""},
                    "edge_type": {"type": "string", "default": "floating"},
                    "data": {"type": "object"},
                },
                "required": ["source", "target"],
            },
        ),
        Tool(
            name="canvas_remove_edge",
            description="Remove an edge from the canvas.",
            inputSchema={
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        ),
        Tool(
            name="canvas_get_state",
            description="Get the full current canvas state — nodes, edges, version, metadata.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="canvas_clear",
            description="Clear the entire canvas (remove all nodes and edges).",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


def _resources() -> list[Resource]:
    return [
        Resource(
            uri=PydAnyUrl("canvas://state"),
            name="Canvas state",
            description="Full canvas state — nodes, edges, version, metadata.",
            mimeType="application/json",
        ),
        Resource(
            uri=PydAnyUrl("canvas://documents"),
            name="Ingested documents",
            description="List of documents available to attach (slug, title, pages, has_gold).",
            mimeType="application/json",
        ),
    ]


# --- Server factory -------------------------------------------------------


def build_server(ops: CanvasOps, registry: SessionRegistry | None = None) -> tuple[Server, SessionRegistry]:
    """Construct an MCP `Server` wired to the given ops backend.

    Returns the server and a `SessionRegistry`. Hosts can broadcast
    `resource_updated` notifications via `registry.broadcast_resource_updated`.
    Handlers track the active session into the registry on every invocation,
    so by the time an agent has called any tool/resource its session is known.
    """
    server: Server = Server("anchor-canvas")
    registry = registry or SessionRegistry()

    def _track() -> None:
        try:
            registry.track(server.request_context.session)
        except Exception:  # pragma: no cover — no active request context
            pass

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        _track()
        return _tools()

    @server.list_resources()
    async def _list_resources() -> list[Resource]:
        _track()
        return _resources()

    @server.read_resource()
    async def _read_resource(uri: AnyUrl) -> str:
        _track()
        s = str(uri)
        if s == "canvas://state":
            return json.dumps(await ops.get_state(), indent=2)
        if s == "canvas://documents":
            return json.dumps(await ops.list_documents(), indent=2)
        raise ValueError(f"Unknown resource: {uri}")

    @server.call_tool()
    async def _call_tool(name: str, args: dict) -> list[TextContent]:
        _track()
        try:
            result = await _dispatch(ops, name, args)
            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        except Exception as e:
            logger.exception("tool %s failed", name)
            return [TextContent(type="text", text=f"Error: {e}")]

    return server, registry


async def _dispatch(ops: CanvasOps, name: str, args: dict) -> Any:
    if name == "canvas_get_state":
        return await ops.get_state()
    if name == "canvas_get_documents":
        return await ops.list_documents()
    if name == "canvas_add_node":
        return await ops.add_node(**args)
    if name == "canvas_update_node":
        node_id = args.pop("id")
        return await ops.update_node(node_id, **args)
    if name == "canvas_remove_node":
        return await ops.remove_node(args["id"])
    if name == "canvas_add_edge":
        return await ops.add_edge(**args)
    if name == "canvas_remove_edge":
        return await ops.remove_edge(args["id"])
    if name == "canvas_clear":
        return await ops.clear()

    # --- Composites ---
    if name == "canvas_attach_document":
        slug = args["slug"]
        idx = await ops.get_document_index(slug)
        title = idx.get("document", {}).get("title", slug) if isinstance(idx, dict) else slug
        pages = idx.get("document", {}).get("page_count", 0) if isinstance(idx, dict) else 0
        return await ops.add_node(
            node_type="document",
            label=title,
            x=args.get("x", 0),
            y=args.get("y", 0),
            data={"slug": slug, "title": title, "page_count": pages},
        )

    if name == "canvas_place_grounded_table":
        doc_id = args["doc_node_id"]
        rows = args["rows"]
        spec_node = await ops.add_node(
            node_type="spec",
            label=args["title"],
            x=args.get("x", 320),
            y=args.get("y", 0),
            data={
                "spec_title": args["title"],
                "parameter_sections": [{"name": args["title"], "rows": rows}],
            },
        )
        spec_id = spec_node["id"]
        edge_specs: list[dict] = []
        for row_index, row in enumerate(rows):
            src = row.get("source") or {}
            if not src:
                continue
            edge_specs.append({
                "source": spec_id,
                "target": doc_id,
                "edge_type": "anchored",
                "label": row.get("parameter", ""),
                "data": {
                    "source_handle": f"spec-row-out-0-{row_index}",
                    "target_handle": "doc-evidence-in",
                    "source_ref": src,
                },
            })
        edges = await ops.add_edges_bulk(edge_specs) if edge_specs else []
        return {"node": spec_node, "evidence_edges": edges}

    if name == "canvas_link_model":
        return await ops.add_edge(
            source=args["model_node_id"],
            target=args["target_id"],
            label=args.get("label", ""),
        )

    raise ValueError(f"Unknown tool: {name}")
