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


def render_plot_image(data: dict[str, Any], width: int = 600, height: int = 350) -> str:
    """Render simulation result as a PNG and return base64-encoded string."""
    import base64
    import plotly.graph_objects as go

    times: list[float] = data.get("time", [])
    signals = [k for k in data if k != "time"]
    COLORS = ["#14b8a6", "#6366f1", "#f59e0b", "#ef4444", "#8b5cf6"]

    fig = go.Figure()
    for i, sig in enumerate(signals):
        fig.add_trace(go.Scatter(
            x=times,
            y=data[sig],
            mode="lines",
            name=sig,
            line=dict(color=COLORS[i % len(COLORS)], width=2),
        ))
    fig.update_layout(
        margin=dict(l=40, r=20, t=20, b=40),
        paper_bgcolor="white",
        plot_bgcolor="white",
        font=dict(size=11),
        legend=dict(orientation="h", y=-0.15),
        xaxis=dict(gridcolor="#e5e7eb", title="time (s)"),
        yaxis=dict(gridcolor="#e5e7eb"),
    )
    img_bytes: bytes = fig.to_image(format="png", width=width, height=height)
    return base64.b64encode(img_bytes).decode()


def sample_data(data: dict[str, Any], max_points: int = 60) -> str:
    """Return a compact CSV-like string of sampled data for LLM context."""
    times: list[float] = data.get("time", [])
    signals = [k for k in data if k != "time"]
    n = len(times)
    if n == 0:
        return "No data."
    step = max(1, n // max_points)
    indices = list(range(0, n, step))[:max_points]
    header = "time," + ",".join(signals)
    rows = []
    for i in indices:
        vals = [f"{times[i]:.3f}"] + [f"{data[s][i]:.4g}" for s in signals]
        rows.append(",".join(vals))
    return header + "\n" + "\n".join(rows)
