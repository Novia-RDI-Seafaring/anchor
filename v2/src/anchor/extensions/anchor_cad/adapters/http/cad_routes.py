"""HTTP routes for the CAD extension.

Mirrors every `cad.*` MCP tool so a non-MCP client (the React Flow
Model3DPrimitive, curl scripts, custom voice/XR clients) can inspect,
list, fetch, and parameter-tweak CAD models. Same `CadService`
methods that MCP calls — adapter is a thin translation layer.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from anchor.extensions.anchor_cad.core.services import CadService

router = APIRouter(prefix="/api/cad", tags=["cad"])

_MIME_BY_EXT = {
    ".stl": "model/stl",
    ".obj": "model/obj",
    ".gltf": "model/gltf+json",
    ".glb": "model/gltf-binary",
    ".3mf": "model/3mf",
    ".ply": "application/x-ply",
    ".step": "application/step",
    ".stp": "application/step",
    ".jscad": "text/javascript",
    ".scad": "text/x-scad",
}


def get_cad_service():  # pragma: no cover  — overridden in app wiring
    raise RuntimeError("get_cad_service dependency not wired")


@router.get("")
async def list_cad(service: CadService = Depends(get_cad_service)) -> JSONResponse:
    models = await service.list_models()
    return JSONResponse([m.model_dump() for m in models])


@router.get("/{slug}")
async def get_cad(slug: str, service: CadService = Depends(get_cad_service)) -> JSONResponse:
    model = await service.get_model(slug)
    if model is None:
        raise HTTPException(404, f"unknown CAD slug: {slug}")
    return JSONResponse(model.model_dump())


@router.get("/{slug}/model")
async def get_cad_file(slug: str, service: CadService = Depends(get_cad_service)) -> FileResponse:
    """Serve the raw model bytes for the 3D viewport (STL, OBJ, glTF, ...)."""
    path = await service.store.get_cad_path(slug)
    if path is None or not path.is_file():
        raise HTTPException(404, f"no model file for slug: {slug}")
    ext = path.suffix.lower()
    mime = _MIME_BY_EXT.get(ext, "application/octet-stream")
    return FileResponse(str(path), media_type=mime, filename=path.name)


@router.post("")
async def inspect(
    file: UploadFile,
    service: CadService = Depends(get_cad_service),
) -> JSONResponse:
    """Upload a CAD file (multipart) and parse its summary.

    Returns the CadModel JSON: parameters, parts, features, dimensions.
    """
    if not file.filename:
        raise HTTPException(400, "uploaded file has no filename")
    body = await file.read()
    try:
        model = await service.upload_and_inspect(body, file.filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return JSONResponse(model.model_dump())


@router.patch("/{slug}/parameters/{parameter_name}")
async def set_parameter(
    slug: str,
    parameter_name: str,
    body: dict[str, Any] = Body(...),
    service: CadService = Depends(get_cad_service),
) -> JSONResponse:
    """Tweak a named parameter on a parametric CAD model.

    Body: `{"value": <new value>}`. Emits CadParameterChanged on the bus
    so any 3D viewport subscribed to the canvas re-renders.
    """
    if "value" not in body:
        raise HTTPException(400, "body must include `value`")
    try:
        model = await service.set_parameter(slug, parameter_name, body["value"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return JSONResponse(model.model_dump())
