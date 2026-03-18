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
            "unit": (v.unit.name if hasattr(v.unit, "name") else str(v.unit)) if getattr(v, "unit", None) else "",
            "description": v.description or "",
        })
    return {
        "model_name": md.modelName,
        "fmi_version": md.fmiVersion,
        "variables": variables,
    }


def _fmu_platforms(path: Path) -> list[str]:
    """Return platform folder names found in the FMU binaries/ directory."""
    import zipfile
    try:
        with zipfile.ZipFile(str(path)) as z:
            return sorted({
                n.split("/")[1]
                for n in z.namelist()
                if n.startswith("binaries/") and n.count("/") >= 2
            })
    except Exception:
        return []


_PLATFORM_NAMES = {
    "win32": "Windows 32-bit", "win64": "Windows 64-bit",
    "linux32": "Linux 32-bit", "linux64": "Linux 64-bit",
    "darwin64": "macOS",
}


def run_simulation(
    filename: str,
    param_overrides: dict[str, float],
    stop_time: float = 10.0,
) -> str:
    """Run FMU simulation synchronously. Returns job_id."""
    import platform
    from fmpy import read_model_description
    from fmpy.simulation import simulate_fmu
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    path = FMU_DIR / filename
    md = read_model_description(str(path))
    output_vars = [v.name for v in md.modelVariables if v.causality == "output"]
    start_values = {k: float(v) for k, v in param_overrides.items()}
    try:
        result = simulate_fmu(
            str(path),
            start_values=start_values,
            stop_time=stop_time,
            output=output_vars or None,
        )
    except Exception as exc:
        if "cannot be simulated on the current platform" in str(exc):
            sys_platform = platform.system()
            current = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(sys_platform, sys_platform)
            fmu_platforms = _fmu_platforms(path)
            friendly = [_PLATFORM_NAMES.get(p, p) for p in fmu_platforms]
            required = ", ".join(friendly) if friendly else "an unsupported platform"
            raise RuntimeError(
                f"This FMU was compiled for {required}, but you are running on {current}. "
                "Re-export the FMU with binaries for your platform to simulate it here."
            ) from exc
        raise
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
