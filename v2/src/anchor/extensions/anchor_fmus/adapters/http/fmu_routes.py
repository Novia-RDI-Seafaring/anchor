"""HTTP routes for the FMU extension — peers of the `fmu.*` MCP tools.

Mirrors every `fmu.*` MCP operation so a non-MCP client (the web canvas,
curl scripts, custom voice agents) can run simulations, inspect models,
and pull results. Same FmuService methods; the adapter is a thin
translation layer.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from anchor.core.upload_safety import UnsafeUploadError, safe_upload_name
from anchor.extensions.anchor_fmus.core.services import FmuService

router = APIRouter(prefix="/api/fmu", tags=["fmu"])

# Most FMU files we've seen are under 50 MB. Allow some headroom.
_MAX_FMU_BYTES = 100 * 1024 * 1024


def get_fmu_service() -> FmuService:  # pragma: no cover — overridden in app wiring
    raise RuntimeError("get_fmu_service dependency not wired")


@router.get("")
async def list_models(service: FmuService = Depends(get_fmu_service)) -> JSONResponse:
    """List every FMU known to this Anchor install with its variables."""
    models = await service.list_models()
    return JSONResponse([m.model_dump() for m in models])


@router.get("/{slug}")
async def get_model(slug: str, service: FmuService = Depends(get_fmu_service)) -> JSONResponse:
    """Return one FMU's model description by slug."""
    model = await service.get_model(slug)
    if model is None:
        raise HTTPException(404, f"unknown FMU: {slug}")
    return JSONResponse(model.model_dump())


@router.post("")
async def inspect(
    file: UploadFile,
    service: FmuService = Depends(get_fmu_service),
) -> JSONResponse:
    """Upload a .fmu file (multipart) and parse its modelDescription.

    Returns the FmuModel JSON: variables, causality, units, defaults.
    """
    try:
        filename = safe_upload_name(file.filename, allowed_extensions={".fmu"})
    except UnsafeUploadError as exc:
        raise HTTPException(400, str(exc))
    body = await file.read()
    if len(body) > _MAX_FMU_BYTES:
        raise HTTPException(413, f"FMU exceeds {_MAX_FMU_BYTES // (1024 * 1024)} MB cap")
    try:
        model = await service.upload_and_inspect(body, filename)
    except ValueError as exc:
        raise HTTPException(400, "could not parse FMU")
    return JSONResponse(model.model_dump())


@router.post("/{slug}/simulate")
async def simulate(
    slug: str,
    body: dict[str, Any] = Body(default_factory=dict),
    service: FmuService = Depends(get_fmu_service),
) -> JSONResponse:
    """Run a simulation. Returns the SimulationRun (id + status).

    Body fields (all optional except slug in the path):
      parameter_overrides: dict of variable_name → value
      stop_time: float (default 1.0)
      output_interval: float (default 0.01)
    """
    try:
        run = await service.simulate(
            slug,
            parameter_overrides=body.get("parameter_overrides"),
            stop_time=float(body.get("stop_time", 1.0)),
            output_interval=float(body.get("output_interval", 0.01)),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return JSONResponse(run.model_dump())


@router.get("/simulations/{simulation_id}/results")
async def get_results(
    simulation_id: str,
    service: FmuService = Depends(get_fmu_service),
) -> JSONResponse:
    """Return the time series for a completed simulation."""
    series = await service.get_series(simulation_id)
    if series is None:
        raise HTTPException(404, f"unknown simulation: {simulation_id}")
    return JSONResponse(series.model_dump())


@router.get("/simulations")
async def list_simulations(
    fmu_slug: str | None = None,
    service: FmuService = Depends(get_fmu_service),
) -> JSONResponse:
    """List simulation runs, optionally filtered to one FMU."""
    runs = await service.list_simulations(fmu_slug)
    return JSONResponse([r.model_dump() for r in runs])
