"""FMU inspection and simulation service."""
import json
import uuid
from pathlib import Path
from typing import Any

FMU_DIR = Path("data/fmus")
RESULT_DIR = Path("data/fmu_results")


def inspect_fmu(filename: str) -> dict[str, Any]:
    """Parse FMU modelDescription and return structured variable list."""
    from fmpy import read_model_description
    FMU_DIR.mkdir(parents=True, exist_ok=True)
    path = FMU_DIR / filename
    md = read_model_description(str(path))
    variables = []
    for v in md.modelVariables:
        variables.append({
            "name": v.name,
            "causality": v.causality,
            "variability": getattr(v, "variability", ""),
            "start": str(v.start) if v.start is not None else "",
            "unit": v.unit.name if getattr(v, "unit", None) else "",
            "description": v.description or "",
        })
    return {
        "model_name": md.modelName,
        "fmi_version": md.fmiVersion,
        "variables": variables,
    }


def run_simulation(
    filename: str,
    param_overrides: dict[str, float],
    stop_time: float = 10.0,
) -> str:
    """Run FMU simulation synchronously. Returns job_id."""
    from fmpy import read_model_description
    from fmpy.simulation import simulate_fmu
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    path = FMU_DIR / filename
    md = read_model_description(str(path))
    output_vars = [v.name for v in md.modelVariables if v.causality == "output"]
    start_values = {k: float(v) for k, v in param_overrides.items()}
    result = simulate_fmu(
        str(path),
        start_values=start_values,
        stop_time=stop_time,
        output_variables=output_vars or None,
    )
    data: dict[str, Any] = {"time": result["time"].tolist()}
    for var in result.dtype.names:
        if var != "time":
            data[var] = result[var].tolist()
    job_id = str(uuid.uuid4())
    (RESULT_DIR / f"{job_id}.json").write_text(json.dumps(data))
    return job_id


def get_result(job_id: str) -> dict[str, Any] | None:
    path = RESULT_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
