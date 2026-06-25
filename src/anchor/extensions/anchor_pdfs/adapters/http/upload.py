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
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from anchor.adapters.http.deps import (
    get_ingest_service,
    get_intent_service,
    get_workspace_service,
)
from anchor.adapters.http.schemas import IngestUploadResponse
from anchor.core.ids import new_event_id, new_id, slugify
from anchor.core.services.intent_service import IntentService
from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.upload_safety import UnsafeUploadError, safe_upload_name
from anchor.extensions.anchor_pdfs.core.services import IngestService

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspaces", tags=["upload"])

# Server-side cap. 200 MB is enough for the largest catalogue PDFs we've
# seen in industry datasheets; uploads above this almost always indicate
# a misclick (video, archive) or an exploit. The check happens after the
# body is read. FastAPI / Starlette buffer to disk, so memory is not exhausted,
# but we still reject before parsing.
_MAX_PDF_BYTES = 200 * 1024 * 1024


def _is_harness_project(request: Request) -> bool:
    """True when this project's ingestion is harness-driven (the agent runs the
    vision extraction, no server-side key). In that mode the server cannot
    ingest the gold layer itself, so drop-to-ingest enqueues an intent instead
    of running the pipeline. Detected from the resolved provider on app config."""
    config = getattr(request.app.state, "anchor_config", None)
    provider = getattr(config, "provider", None) if config is not None else None
    return (provider or "").lower() == "harness"


@router.post("/{slug}/upload")
async def upload(
    slug: str,
    request: Request,
    file: UploadFile = File(...),
    x: float = Form(0.0),
    y: float = Form(0.0),
    ingest: IngestService = Depends(get_ingest_service),
    workspace: WorkspaceService = Depends(get_workspace_service),
    intents: IntentService = Depends(get_intent_service),
) -> IngestUploadResponse:
    try:
        filename = safe_upload_name(file.filename, allowed_extensions={".pdf"})
    except UnsafeUploadError as exc:
        raise HTTPException(400, str(exc)) from exc
    pdf_bytes = await file.read()
    if len(pdf_bytes) > _MAX_PDF_BYTES:
        raise HTTPException(413, f"PDF exceeds {_MAX_PDF_BYTES // (1024 * 1024)} MB cap")
    doc_slug = slugify(Path(filename).stem)
    job_id = new_event_id()
    node_id = new_id()
    queued_at = time.time()
    harness = _is_harness_project(request)

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
            # In harness mode the agent must run the ingest; reflect that the
            # node is waiting on the agent rather than being pipeline-queued.
            "status": "awaiting_agent" if harness else "pending",
            "job_id": job_id,
            "ingest_stage": "awaiting_agent" if harness else "queued",
            "ingest_stage_label": "awaiting agent" if harness else "queued",
            "ingest_progress": 0,
            "ingest_started_at": queued_at,
            "ingest_updated_at": queued_at,
        },
    )

    if harness:
        # Harness ingestion: the server has no vision key, so it cannot run the
        # gold stage. Bronze is stashed so the agent can fetch the raw PDF, then
        # a project-level drop_to_ingest intent is enqueued (firing the
        # IntentPending signal). The agent pulls it and runs ingest_begin ->
        # submit_page -> finalize, then resolve_intent. (Issue #148.)
        try:
            await ingest.store.stash_bronze(pdf_bytes, filename)
        except Exception:  # noqa: BLE001 - enqueue even if stash is unavailable
            log.exception("drop-to-ingest: bronze stash failed (continuing to enqueue)")
        intent = await intents.enqueue(
            "drop_to_ingest",
            origin_canvas_id=slug,
            payload={
                "slug": doc_slug,
                "filename": filename,
                "node_id": node_id,
                "workspace_id": slug,
                "job_id": job_id,
            },
        )
        return IngestUploadResponse(
            slug=doc_slug, job_id=job_id, status="awaiting_agent", intent_id=intent.id
        )

    async def _run() -> None:
        try:
            started_at = time.time()
            await workspace.update_node(slug, node_id, {
                "status": "ingesting",
                "ingest_stage": "starting",
                "ingest_stage_label": "starting ingest",
                "ingest_progress": 1,
                "ingest_started_at": started_at,
                "ingest_updated_at": started_at,
            })
            summary = await ingest.ingest_pdf(pdf_bytes, filename, slug=doc_slug, workspace_id=slug)
            finished_at = time.time()
            await workspace.update_node(slug, node_id, {
                "status": "ready",
                "page_count": summary.get("page_count", 0),
                "region_count": summary.get("region_count", 0),
                "embedded_count": summary.get("embedded_count", 0),
                "ingest_stage": "complete",
                "ingest_stage_label": "complete",
                "ingest_progress": 100,
                "ingest_updated_at": finished_at,
                "ingest_finished_at": finished_at,
            })
        except Exception as exc:
            log.exception("upload-and-ingest failed")
            try:
                finished_at = time.time()
                await workspace.update_node(slug, node_id, {
                    "status": "failed",
                    "error": str(exc),
                    "ingest_stage": "failed",
                    "ingest_stage_label": "failed",
                    "ingest_updated_at": finished_at,
                    "ingest_finished_at": finished_at,
                })
            except Exception:
                # The ingest error is already logged; a best-effort status
                # update must not crash the background task.
                pass

    asyncio.create_task(_run())
    return IngestUploadResponse(slug=doc_slug, job_id=job_id, status="started")
