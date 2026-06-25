"""FastAPI app builder — wires services into routers."""
from __future__ import annotations

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
    sse,
    status,
    workspaces,
)
from anchor.core.clock import SystemClock
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
from anchor.infra.config import AnchorConfig


def build_app(
    *,
    workspace_service: WorkspaceService,
    ingest_service: IngestService,
    doc_store: DocStore,
    bus: EventBus,
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
    app = FastAPI(title="Anchor v2", version="0.2.0")
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
                FsIntentStore(data_dir), bus, now=SystemClock().now
            )
    app.state.intent_service = intent_service
    app.state.cad_service = cad_service
    app.state.sysml_service = sysml_service
    app.state.synopsis_service = synopsis_service
    app.state.ingest_session_service = ingest_session_service
    app.state.anchor_config = config

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

    app.include_router(workspaces.router)
    app.include_router(nodes.router)
    app.include_router(edges.router)
    app.include_router(documents.router)
    app.include_router(ingest_sessions.router)
    app.include_router(upload.router)
    app.include_router(sse.router)
    app.include_router(ingests.router)
    app.include_router(intents.router)
    app.include_router(status.router)
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
