"""Drop-to-ingest: POST a PDF to a workspace, place a placeholder document
node immediately, kick off ingest, and finalize the node when the pipeline
completes.

The placeholder node carries `data.status` ∈ {pending, ingesting, ready,
failed} so DocumentNode renders a status badge that updates as SSE events
arrive (`IngestProgress`, `DocIngested`, `DocIngestFailed`).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from anchor.adapters.http.deps import get_ingest_service, get_workspace_service
from anchor.adapters.http.schemas import IngestUploadResponse
from anchor.core.ids import new_event_id, new_id, slugify
from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.upload_safety import UnsafeUploadError, safe_upload_name
from anchor.extensions.anchor_pdfs.core.services import IngestService

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspaces", tags=["upload"])

# Server-side cap. 200 MB is enough for the largest catalogue PDFs we've
# seen in industry datasheets; uploads above this almost always indicate
# a misclick (video, archive) or an exploit. The check happens after the
# body is read — FastAPI / Starlette buffer to disk, so memory is not
# exhausted, but we still reject before parsing.
_MAX_PDF_BYTES = 200 * 1024 * 1024


@router.post("/{slug}/upload")
async def upload(
    slug: str,
    file: UploadFile = File(...),
    x: float = Form(0.0),
    y: float = Form(0.0),
    ingest: IngestService = Depends(get_ingest_service),
    workspace: WorkspaceService = Depends(get_workspace_service),
) -> IngestUploadResponse:
    try:
        filename = safe_upload_name(file.filename, allowed_extensions={".pdf"})
    except UnsafeUploadError as exc:
        raise HTTPException(400, str(exc))
    pdf_bytes = await file.read()
    if len(pdf_bytes) > _MAX_PDF_BYTES:
        raise HTTPException(413, f"PDF exceeds {_MAX_PDF_BYTES // (1024 * 1024)} MB cap")
    doc_slug = slugify(Path(filename).stem)
    job_id = new_event_id()
    node_id = new_id()

    await workspace.add_node(
        slug,
        id=node_id,
        node_type="document",
        label=filename,
        x=float(x),
        y=float(y),
        data={
            "slug": doc_slug,
            "filename": filename,
            "status": "pending",
            "job_id": job_id,
        },
    )

    async def _run() -> None:
        try:
            await workspace.update_node(slug, node_id, {"status": "ingesting"})
            summary = await ingest.ingest_pdf(pdf_bytes, filename, slug=doc_slug, workspace_id=slug)
            await workspace.update_node(slug, node_id, {
                "status": "ready",
                "page_count": summary.get("page_count", 0),
                "region_count": summary.get("region_count", 0),
            })
        except Exception as exc:
            log.exception("upload-and-ingest failed")
            try:
                await workspace.update_node(slug, node_id, {
                    "status": "failed", "error": str(exc),
                })
            except Exception:
                pass

    asyncio.create_task(_run())
    return IngestUploadResponse(slug=doc_slug, job_id=job_id, status="started")
