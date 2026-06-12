"""Harness ingest sessions over HTTP - parity with the MCP/CLI protocol.

JSON in, JSON out, loopback-only like the rest of the server. The PDF is
named by path (the server and the harness share a host); off-machine
agents should drive the MCP surface with format=base64 instead.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ingest/sessions", tags=["ingest-sessions"])


def _svc(request: Request):
    svc = getattr(request.app.state, "ingest_session_service", None)
    if svc is None:
        raise HTTPException(503, "harness ingest sessions not configured")
    return svc


class BeginSessionBody(BaseModel):
    pdf_path: str
    slug: str | None = None
    dpi: int | None = None
    force: bool = False


class SubmitPageBody(BaseModel):
    regions: list[dict[str, Any]] = Field(default_factory=list)
    polished_md: str | None = None
    protocol_version: int | None = None


class FinalizeBody(BaseModel):
    allow_missing_pages: list[int] | None = None
    declared_model: str | None = None


@router.post("", status_code=201)
async def begin_session(body: BeginSessionBody, request: Request):
    svc = _svc(request)
    path = Path(body.pdf_path).expanduser()
    if not path.is_file():
        raise HTTPException(404, f"PDF not found: {path}")
    return await svc.ingest_begin(
        path.read_bytes(), path.name,
        slug=body.slug, dpi=body.dpi, force=body.force,
    )


@router.get("")
async def session_status_by_slug(
    request: Request,
    slug: str = Query(..., description="Document slug to look up the session for."),
):
    svc = _svc(request)
    out = await svc.ingest_status(slug=slug)
    if "error" in out:
        raise HTTPException(404, out["error"])
    return out


@router.get("/{session_id}")
async def session_status(session_id: str, request: Request):
    svc = _svc(request)
    out = await svc.ingest_status(session_id)
    if "error" in out:
        raise HTTPException(404, out["error"])
    return out


@router.get("/{session_id}/pages/{page}")
async def get_page(
    session_id: str,
    page: int,
    request: Request,
    format: str = Query("path", pattern="^(path|base64)$"),
):
    svc = _svc(request)
    item = await svc.ingest_get_page(session_id, page)
    if "error" in item:
        raise HTTPException(404, item["error"])
    image_path = item.pop("image_path", None)
    # Same byte-fetch envelope the MCP surface uses: a same-host agent
    # reads the path; format=base64 inlines the bytes.
    if image_path is None:
        item["image"] = {"error": "not found"}
    elif format == "base64":
        raw = Path(image_path).read_bytes()
        item["image"] = {
            "format": "base64",
            "value": base64.b64encode(raw).decode("ascii"),
            "content_type": "image/png",
            "size_bytes": len(raw),
        }
    else:
        item["image"] = {"format": "path", "value": image_path, "content_type": "image/png"}
    return item


@router.put("/{session_id}/pages/{page}")
async def submit_page(session_id: str, page: int, body: SubmitPageBody, request: Request):
    svc = _svc(request)
    # Verdicts (accepted or not) come back as 200 + {accepted, errors?} so
    # the agent loop stays uniform across MCP/HTTP/CLI.
    return await svc.ingest_submit_page(
        session_id, page,
        regions=body.regions,
        polished_md=body.polished_md,
        protocol_version=body.protocol_version,
    )


@router.post("/{session_id}/finalize")
async def finalize_session(session_id: str, request: Request, body: FinalizeBody | None = None):
    svc = _svc(request)
    body = body or FinalizeBody()
    return await svc.ingest_finalize(
        session_id,
        allow_missing_pages=body.allow_missing_pages,
        declared_model=body.declared_model,
    )


@router.delete("/{session_id}")
async def abort_session(session_id: str, request: Request):
    svc = _svc(request)
    out = await svc.ingest_abort(session_id)
    if not out.get("aborted"):
        raise HTTPException(404, out.get("error", "abort failed"))
    return out
