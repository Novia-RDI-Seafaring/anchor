"""Runtime status endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from anchor.adapters.extension_host import extension_status_payload
from anchor.adapters.http.deps import get_doc_store, get_workspace_service
from anchor.adapters.status import build_status_summary
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.infra.config import AnchorConfig

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/extensions/status")
async def get_extension_status(request: Request):
    """Return extension diagnostics: bundled runtimes + discovered producers.

    Bundled runtime entries reflect actual startup; discovered system/project
    OIP producers get a static PATH check on their `invocation.command` and
    are marked `started: false` (Anchor never spawns them; the harness does).
    """
    statuses = getattr(request.app.state, "extension_status", {})
    config = getattr(request.app.state, "anchor_config", None)
    data_dir = getattr(config, "data_dir", None)
    return extension_status_payload(statuses, data_dir)


@router.get("/status")
async def get_status(
    request: Request,
    workspace: WorkspaceService = Depends(get_workspace_service),
    doc_store: DocStore = Depends(get_doc_store),
):
    config = getattr(request.app.state, "anchor_config", None)
    if config is None:
        config = AnchorConfig()
    return await build_status_summary(
        config=config,
        workspace=workspace,
        doc_store=doc_store,
    )
