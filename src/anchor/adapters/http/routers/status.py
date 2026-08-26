"""Runtime status endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from anchor.adapters.extension_host import extension_runtime_status_payload
from anchor.adapters.http.deps import get_doc_store, get_workspace_service
from anchor.adapters.status import build_status_summary
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.infra.config import AnchorConfig

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/extensions/status")
async def get_extension_status(request: Request):
    """Return bundled extension startup diagnostics for this runtime."""
    statuses = getattr(request.app.state, "extension_status", {})
    return extension_runtime_status_payload(statuses)


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
