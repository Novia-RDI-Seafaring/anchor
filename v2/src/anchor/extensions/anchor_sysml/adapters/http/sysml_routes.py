"""HTTP routes for the SysML extension.

Two endpoints:

  * ``POST /api/sysml/render`` — body: ``{workspace_slug, text, x_offset?,
    y_offset?, filename?}`` → returns ``SysmlRenderResult`` (node ids, edge
    ids, diagnostics).
  * ``GET /api/sysml/export?workspace_slug=…`` — returns ``{text}``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from anchor.extensions.anchor_sysml.core.services import SysmlService

router = APIRouter(prefix="/api/sysml", tags=["sysml"])


def get_sysml_service():  # pragma: no cover  — overridden in app wiring
    raise RuntimeError("get_sysml_service dependency not wired")


class RenderRequest(BaseModel):
    workspace_slug: str
    text: str
    x_offset: float = 0
    y_offset: float = 0
    filename: str | None = None


@router.post("/render")
async def render_sysml(
    body: RenderRequest,
    service: SysmlService = Depends(get_sysml_service),
) -> JSONResponse:
    result = await service.render(
        workspace_slug=body.workspace_slug,
        text=body.text,
        x_offset=body.x_offset,
        y_offset=body.y_offset,
        filename=body.filename,
    )
    return JSONResponse(result.model_dump())


@router.get("/export")
async def export_sysml(
    workspace_slug: str,
    service: SysmlService = Depends(get_sysml_service),
) -> JSONResponse:
    text = await service.export(workspace_slug=workspace_slug)
    payload: dict[str, Any] = {"workspace_slug": workspace_slug, "text": text}
    return JSONResponse(payload)
