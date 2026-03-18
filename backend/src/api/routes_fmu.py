"""FMU upload, simulate, and result retrieval routes."""
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from ..fmu.service import FMU_DIR, inspect_fmu, run_simulation, get_result

router = APIRouter(prefix="/api/fmu", tags=["fmu"])


@router.post("/upload")
async def upload_fmu(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".fmu"):
        raise HTTPException(400, "Only .fmu files accepted")
    FMU_DIR.mkdir(parents=True, exist_ok=True)
    dest = FMU_DIR / file.filename
    dest.write_bytes(await file.read())
    info = inspect_fmu(file.filename)
    return {"filename": file.filename, **info}


@router.get("/inspect/{filename}")
async def inspect_fmu_route(filename: str):
    try:
        return inspect_fmu(filename)
    except Exception as e:
        raise HTTPException(404, str(e))


class SimulateRequest(BaseModel):
    filename: str
    param_overrides: dict[str, float] = {}
    stop_time: float = 10.0


@router.post("/simulate")
async def simulate(req: SimulateRequest):
    try:
        job_id = run_simulation(req.filename, req.param_overrides, req.stop_time)
        return {"job_id": job_id}
    except Exception as e:
        raise HTTPException(422, str(e))


@router.get("/result/{job_id}")
async def result(job_id: str):
    data = get_result(job_id)
    if data is None:
        raise HTTPException(404, "Result not found")
    return data
