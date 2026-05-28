"""Real FMU runtime backed by FMPy.

Lazy-imports FMPy so installing the extension without FMPy installed
doesn't break import. Users opt in via:

    pip install 'anchor-kb[fmus]'      # or
    pip install fmpy>=0.3.22

If FMPy isn't installed, instantiating this class raises a clear
ImportError. The extension's service factory falls back to FakeFmuRuntime
in that case so tests + demos still run.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from anchor.extensions.anchor_fmus.core.ports import FmuRuntime
from anchor.extensions.anchor_fmus.core.schemas import (
    FmuModel,
    FmuVariable,
    SimulationRun,
    TimeSeries,
)


class FmpyFmuRuntime(FmuRuntime):
    synthetic = False

    def __init__(self) -> None:
        try:
            import fmpy  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "FMPy is not installed. Install with `pip install 'anchor-kb[fmus]'` "
                "or `pip install fmpy>=0.3.22`. Or use FakeFmuRuntime for offline use."
            ) from exc

    async def inspect(self, fmu_path: Path) -> FmuModel:
        return await asyncio.to_thread(_inspect_sync, fmu_path)

    async def simulate(
        self,
        fmu_path: Path,
        *,
        run: SimulationRun,
        on_progress: object | None = None,
    ) -> TimeSeries:
        return await asyncio.to_thread(_simulate_sync, fmu_path, run)


def _inspect_sync(fmu_path: Path) -> FmuModel:
    import fmpy
    md = fmpy.read_model_description(str(fmu_path))
    variables = [_var_from_fmpy(v) for v in md.modelVariables]
    return FmuModel(
        slug="",
        filename=fmu_path.name,
        model_name=md.modelName or "",
        description=md.description or "",
        fmi_version=md.fmiVersion,
        platforms=_detect_platforms(fmu_path),
        variables=variables,
    )


def _simulate_sync(fmu_path: Path, run: SimulationRun) -> TimeSeries:
    import fmpy
    result = fmpy.simulate_fmu(
        str(fmu_path),
        stop_time=run.stop_time,
        output_interval=run.output_interval,
        start_values=run.parameter_overrides,
    )
    # `result` is a numpy structured array; first column is time, others are output vars.
    column_names = list(result.dtype.names) if result.dtype.names else []
    time_col = result["time"].tolist() if "time" in column_names else []
    variables: dict[str, list[float]] = {}
    for name in column_names:
        if name == "time":
            continue
        variables[name] = result[name].tolist()
    return TimeSeries(simulation_id=run.id, time=time_col, variables=variables)


def _var_from_fmpy(v: Any) -> FmuVariable:
    causality_str: str = getattr(v, "causality", "local") or "local"
    variability_str: str = getattr(v, "variability", "continuous") or "continuous"
    type_obj = getattr(v, "type", None)
    type_str = getattr(type_obj, "__class__", type(None)).__name__.replace("Variable", "") or "Real"
    if type_str not in ("Real", "Integer", "Boolean", "String"):
        type_str = "Real"
    start = getattr(v, "start", None)
    return FmuVariable(
        name=v.name,
        causality=causality_str,  # type: ignore[arg-type]
        variability=variability_str,  # type: ignore[arg-type]
        description=getattr(v, "description", "") or "",
        unit=getattr(v, "unit", None),
        start=start,
        type=type_str,  # type: ignore[arg-type]
    )


def _detect_platforms(fmu_path: Path) -> list[str]:
    """Peek into the FMU zip and report which native binary platforms are bundled."""
    import zipfile
    out: list[str] = []
    try:
        with zipfile.ZipFile(fmu_path) as zf:
            for name in zf.namelist():
                if name.startswith("binaries/") and name.endswith(("/", ".dylib", ".dll", ".so")):
                    parts = name.split("/")
                    if len(parts) >= 2:
                        platform = parts[1]
                        if platform and platform not in out:
                            out.append(platform)
    except (zipfile.BadZipFile, OSError):
        # Platform metadata is advisory; corrupt/unreadable FMUs are handled
        # later by the real inspection path.
        pass
    return out
