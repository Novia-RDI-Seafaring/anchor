"""FastAPI app builder — wires services into routers."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from anchor.adapters.http.routers import edges, nodes, sse, workspaces
from anchor.core.ports.event_bus import EventBus
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_cad.adapters.http import cad_routes
from anchor.extensions.anchor_cad.core.services import CadService
from anchor.extensions.anchor_pdfs.adapters.http import documents, upload
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService


def build_app(
    *,
    workspace_service: WorkspaceService,
    ingest_service: IngestService,
    doc_store: DocStore,
    bus: EventBus,
    static_dir: Path | None = None,
    cad_service: CadService | None = None,
) -> FastAPI:
    app = FastAPI(title="Anchor v2", version="0.2.0")
    app.state.workspace_service = workspace_service
    app.state.ingest_service = ingest_service
    app.state.doc_store = doc_store
    app.state.bus = bus
    app.state.cad_service = cad_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(workspaces.router)
    app.include_router(nodes.router)
    app.include_router(edges.router)
    app.include_router(documents.router)
    app.include_router(upload.router)
    app.include_router(sse.router)
    if cad_service is not None:
        app.dependency_overrides[cad_routes.get_cad_service] = lambda: cad_service
        app.include_router(cad_routes.router)

    if static_dir is not None and static_dir.is_dir():
        index = static_dir / "index.html"

        @app.get("/")
        async def root() -> FileResponse:
            return FileResponse(index)

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str) -> FileResponse:
            target = static_dir / full_path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(index)

        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app
