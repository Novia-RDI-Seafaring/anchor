"""Agent tools for FMU inspection and simulation."""
from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext
from ..deps import AgentDeps
from ..state import CanvasNode, FmuVariable
from ..helpers import _snapshot, _mark_node_for_run, _ensure_relation


async def inspect_fmu_tool(
    ctx: RunContext[AgentDeps],
    filename: str,
) -> ToolReturn:
    """Inspect an uploaded FMU file and add an FMU node to the canvas.

    Returns the node id and a summary of inputs, outputs and parameters.
    """
    from src.fmu.service import inspect_fmu
    info = inspect_fmu(filename)
    variables = [FmuVariable(**v) for v in info["variables"]]

    node = CanvasNode(
        node_type="fmu",
        title=info["model_name"],
        fmu_filename=filename,
        fmu_model_name=info["model_name"],
        fmu_variables=variables,
        status="found",
    )
    _mark_node_for_run(node, ctx)
    ctx.deps.state.nodes.append(node)
    result = _snapshot(ctx)

    inputs = [v for v in variables if v.causality == "input"]
    outputs = [v for v in variables if v.causality == "output"]
    params = [v for v in variables if v.causality == "parameter"]
    result.return_value = {
        "node_id": node.id,
        "model_name": info["model_name"],
        "fmi_version": info["fmi_version"],
        "inputs": [v.name for v in inputs],
        "outputs": [v.name for v in outputs],
        "parameters": {v.name: v.start for v in params},
    }
    return result


async def simulate_fmu_tool(
    ctx: RunContext[AgentDeps],
    filename: str,
    fmu_node_id: str = "",
    param_overrides: dict[str, float] | None = None,
    stop_time: float = 10.0,
) -> ToolReturn:
    """Run a simulation of an FMU and add a plot node to the canvas.

    param_overrides: dict of parameter name -> value to override start values.
    stop_time: simulation end time in seconds.
    Returns job_id and the plot node id.
    """
    from src.fmu.service import run_simulation
    job_id = run_simulation(filename, param_overrides or {}, stop_time)

    # Find output signal names
    existing_fmu = next(
        (n for n in ctx.deps.state.nodes if n.node_type == "fmu" and n.fmu_filename == filename),
        None,
    )
    signal_names = (
        [v.name for v in existing_fmu.fmu_variables if v.causality == "output"]
        if existing_fmu else []
    )

    plot = CanvasNode(
        node_type="plot",
        title=f"{filename} — output",
        plot_job_id=job_id,
        plot_fmu_filename=filename,
        plot_signal_names=signal_names,
        plot_stop_time=stop_time,
        status="found",
    )
    _mark_node_for_run(plot, ctx)
    ctx.deps.state.nodes.append(plot)

    if fmu_node_id:
        _ensure_relation(ctx, fmu_node_id, plot.id, label="output")

    result = _snapshot(ctx)
    result.return_value = {
        "job_id": job_id,
        "plot_node_id": plot.id,
        "signals": signal_names,
        "stop_time": stop_time,
    }
    return result
