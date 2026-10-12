"""FastAPI app builder — wires services into routers."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from anchor.adapters.http.routers import (
    edges,
    ingests,
    intents,
    nodes,
    projects,
    realtime,
    sse,
    status,
    whoami,
    workspaces,
)
from anchor.adapters.project_runtime import ProjectRuntime, bind_workspace_sources
from anchor.core.clock import SystemClock
from anchor.core.events.actor import Actor, actor_scope
from anchor.core.ids import InvalidWorkspaceSlugError
from anchor.core.ports.event_bus import EventBus
from anchor.core.services.intent_service import IntentService
from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.upload_safety import UnsafeUploadError
from anchor.extensions.anchor_cad.adapters.http import cad_routes
from anchor.extensions.anchor_cad.core.services import CadService
from anchor.extensions.anchor_fmus.adapters.http import fmu_routes
from anchor.extensions.anchor_fmus.core.services import FmuService
from anchor.extensions.anchor_pdfs.adapters.http import documents, ingest_sessions, upload
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_sysml.adapters.http import sysml_routes
from anchor.extensions.anchor_sysml.core.services import SysmlService
from anchor.infra.activity import ActivityLog
from anchor.infra.config import AnchorConfig


class _ActorAttributionMiddleware:
    """Attribute every HTTP write to ``{kind: human, label: browser}`` (#322).

    Pure ASGI (no BaseHTTPMiddleware task hop) so the ``ContextVar`` set
    here is visible inside route handlers and the service calls they await.
    Routes whose request body carries an explicit ``actor`` override the
    default for their own call.
    """

    def __init__(self, app) -> None:  # noqa: ANN001 -- ASGI app
        self._app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        with actor_scope(Actor(kind="human", label="browser")):
            await self._app(scope, receive, send)


class _ActivityMiddleware:
    """Write one line per API call to the project's activity log.

    What it records is the cost of an agent's work in the unit that
    matters: calls. Pure ASGI, like the actor middleware, so it adds no
    task hop; the event stream and the log's own endpoint are left out.
    """

    SKIP = {"/api/intents/events", "/api/activity", "/api/status"}

    def __init__(self, app, log) -> None:  # noqa: ANN001 -- ASGI app, ActivityLog
        self._app = app
        self._log = log

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if (
            self._log is None
            or scope["type"] != "http"
            or not path.startswith("/api/")
            or path in self.SKIP
            or path.endswith("/events")
        ):
            await self._app(scope, receive, send)
            return
        started = time.perf_counter()
        status = {"code": 0}

        async def _send(message):  # noqa: ANN001
            if message.get("type") == "http.response.start":
                status["code"] = int(message.get("status", 0))
            await send(message)

        try:
            await self._app(scope, receive, _send)
        finally:
            parts = path.split("/")
            intent = parts[3] if len(parts) > 3 and parts[2] == "intents" and parts[3] not in ("all", "events") else None
            self._log.record(
                kind="http",
                name=f"{scope.get('method', '')} {_route_shape(path)}",
                ms=round((time.perf_counter() - started) * 1000, 1),
                status=status["code"],
                intent=intent,
            )


def _route_shape(path: str) -> str:
    """The path with ids and slugs blanked, so calls group by what they do."""
    parts = path.split("/")
    out: list[str] = []
    for i, part in enumerate(parts):
        prev = parts[i - 1] if i else ""
        if prev in ("intents", "items", "workspaces", "nodes", "edges", "documents", "pages", "proposal-sets", "references", "projects") and part not in ("all", "events"):
            out.append("{}")
        else:
            out.append(part)
    return "/".join(out)


def build_app(
    runtime: ProjectRuntime | None = None,
    *,
    workspace_service: WorkspaceService | None = None,
    ingest_service: IngestService | None = None,
    doc_store: DocStore | None = None,
    bus: EventBus | None = None,
    intent_service: IntentService | None = None,
    static_dir: Path | None = None,
    cad_service: CadService | None = None,
    sysml_service: SysmlService | None = None,
    synopsis_service: object | None = None,
    ingest_session_service: object | None = None,
    fmu_service: FmuService | None = None,
    canvases_dir: Path | None = None,
    config: AnchorConfig | None = None,
) -> FastAPI:
    extension_status = {}
    if runtime is not None:
        workspace_service = runtime.workspace
        ingest_service = runtime.require_ingest()
        doc_store = runtime.doc_store
        bus = runtime.bus
        intent_service = runtime.intents
        cad_service = runtime.cad
        sysml_service = runtime.sysml
        synopsis_service = runtime.synopsis
        ingest_session_service = runtime.ingest_session
        fmu_service = runtime.fmu
        canvases_dir = runtime.config.canvases_dir
        config = runtime.config
        extension_status = runtime.extension_status

    if (
        workspace_service is None
        or ingest_service is None
        or doc_store is None
        or bus is None
    ):
        raise ValueError("build_app requires a ProjectRuntime or explicit core services")

    # Canvas presence (#322 follow-up): per-serve-process, in-memory roster
    # of SSE viewers + recently-writing agents. The SSE router registers
    # connections; this lifespan runs a bus-firehose feed that counts
    # agent-actor writes as presence. Nothing is persisted — presence is
    # ephemeral by definition, and a second serve process has its own
    # separate roster.
    from anchor.infra.presence import PresenceTracker

    presence_tracker = PresenceTracker()
    feed_bus = bus

    @asynccontextmanager
    async def _lifespan(_app: FastAPI):
        async def feed() -> None:
            async for evt in feed_bus.subscribe(None):
                presence_tracker.note_event(evt)

        task = asyncio.create_task(feed(), name="presence-feed")
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            presence_tracker.close()

    app = FastAPI(title="Anchor v2", version="0.2.0", lifespan=_lifespan)
    app.state.presence = presence_tracker
    bind_workspace_sources(workspace_service, doc_store)
    app.state.workspace_service = workspace_service
    app.state.ingest_service = ingest_service
    app.state.doc_store = doc_store
    app.state.bus = bus
    # The intent queue rides the same bus; build a default fs-backed service
    # when the caller did not supply one so the surface is always wired.
    if intent_service is None:
        from anchor.infra.stores.fs_intent_store import FsIntentStore

        data_dir = canvases_dir.parent if canvases_dir is not None else None
        if data_dir is not None:
            intent_service = IntentService(
                FsIntentStore(data_dir), bus, now=SystemClock().now,
                workspace=workspace_service,
            )
    app.state.intent_service = intent_service
    app.state.cad_service = cad_service
    app.state.sysml_service = sysml_service
    app.state.synopsis_service = synopsis_service
    app.state.ingest_session_service = ingest_session_service
    app.state.anchor_config = config
    app.state.extension_status = extension_status
    # The activity log lives beside the canvases, where the CLI and an MCP
    # session find the same file.
    activity_dir = runtime.config.data_dir if runtime is not None else (
        canvases_dir.parent if canvases_dir is not None else None
    )
    app.state.activity = ActivityLog(activity_dir) if activity_dir is not None else None

    # Bridge cross-process writes (CLI / MCP-stdio in another process) into
    # this app's bus by tailing each workspace's events.jsonl. SSE router
    # calls registry.ensure(slug) lazily on the first subscriber.
    if canvases_dir is not None:
        from anchor.infra.bus.event_tailer import TailerRegistry
        app.state.tailer_registry = TailerRegistry(canvases_root=canvases_dir, bus=bus)
    else:
        app.state.tailer_registry = None

    # CORS: this server runs same-origin behind the SPA mount in production,
    # so no CORS headers are needed there. During development the Vite dev
    # server on http://localhost:5173 proxies API calls, which means it
    # too is technically same-origin from the browser's POV — but if a
    # contributor runs Vite without the proxy we still want it to work.
    # We therefore allow only the documented dev origins and let users
    # override via ANCHOR_CORS_ORIGINS for unusual deployments.
    import os
    extra_origins = [
        o.strip()
        for o in os.environ.get("ANCHOR_CORS_ORIGINS", "").split(",")
        if o.strip()
    ]
    cors_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        *extra_origins,
    ]
    # Default actor for every request (#322). Added after CORS so it wraps
    # the routers directly; a request-body `actor` still overrides per-call.
    app.add_middleware(_ActorAttributionMiddleware)
    app.add_middleware(_ActivityMiddleware, log=app.state.activity)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(InvalidWorkspaceSlugError)
    async def _invalid_slug(_req: Request, exc: InvalidWorkspaceSlugError) -> JSONResponse:
        # Surfaces both boundary validation and the defence-in-depth check
        # inside FsWorkspaceStore as a consistent 400.
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(UnsafeUploadError)
    async def _unsafe_upload(_req: Request, exc: UnsafeUploadError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    app.include_router(projects.router)
    app.include_router(workspaces.router)
    app.include_router(nodes.router)
    app.include_router(nodes.node_types_router)
    app.include_router(edges.router)
    app.include_router(documents.router)
    app.include_router(ingest_sessions.router)
    app.include_router(upload.router)
    app.include_router(sse.router)
    app.include_router(realtime.router)
    app.include_router(ingests.router)
    app.include_router(intents.router)
    app.include_router(status.router)
    app.include_router(whoami.router)
    if cad_service is not None:
        app.dependency_overrides[cad_routes.get_cad_service] = lambda: cad_service
        app.include_router(cad_routes.router)
    if sysml_service is not None:
        app.dependency_overrides[sysml_routes.get_sysml_service] = lambda: sysml_service
        app.include_router(sysml_routes.router)
    if fmu_service is not None:
        app.dependency_overrides[fmu_routes.get_fmu_service] = lambda: fmu_service
        app.include_router(fmu_routes.router)

    if static_dir is not None and static_dir.is_dir():
        index = static_dir / "index.html"
        static_root = static_dir.resolve()

        @app.get("/")
        async def root() -> FileResponse:
            return FileResponse(index)

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            # Containment: a crafted request like ``/api/../../../etc/passwd``
            # would otherwise resolve to an arbitrary file on disk. Resolve
            # the candidate and only serve it when it stays under the
            # static bundle root; any traversal falls through to the SPA
            # index, which is the safe default for an unknown route.
            target = (static_dir / full_path).resolve()
            try:
                target.relative_to(static_root)
            except ValueError:
                return FileResponse(index)
            if target.is_file():
                return FileResponse(target)
            return FileResponse(index)

        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app
