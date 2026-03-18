"""Agent tools for FMU inspection and simulation."""
import os
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

    If an fmu node with this filename already exists on canvas, returns its info
    without creating a duplicate. Returns the node id and a summary of inputs,
    outputs and parameters.
    """
    # Reuse existing node if already on canvas
    existing = next(
        (n for n in ctx.deps.state.nodes if n.node_type == "fmu" and n.fmu_filename == filename),
        None,
    )
    if existing:
        inputs = [v for v in existing.fmu_variables if v.causality == "input"]
        outputs = [v for v in existing.fmu_variables if v.causality == "output"]
        params = [v for v in existing.fmu_variables if v.causality == "parameter"]
        result = _snapshot(ctx)
        result.return_value = {
            "node_id": existing.id,
            "model_name": existing.fmu_model_name,
            "inputs": [v.name for v in inputs],
            "outputs": [v.name for v in outputs],
            "parameters": {v.name: v.start for v in params},
            "note": "reused existing canvas node",
        }
        return result

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

    # Merge default parameter values from FMU with any overrides so the plot
    # node always records the actual values used, even when nothing was overridden.
    default_params: dict[str, float] = {}
    if existing_fmu:
        for v in existing_fmu.fmu_variables:
            if v.causality == "parameter" and v.start:
                try:
                    default_params[v.name] = float(v.start)
                except (ValueError, TypeError):
                    pass
    params = {**default_params, **(param_overrides or {})}
    param_label = ", ".join(f"{k}={v:g}" for k, v in params.items()) if params else ""

    plot = CanvasNode(
        node_type="plot",
        title=f"{filename} — output",
        plot_job_id=job_id,
        plot_fmu_filename=filename,
        plot_signal_names=signal_names,
        plot_stop_time=stop_time,
        plot_param_values=params,
        status="found",
    )
    _mark_node_for_run(plot, ctx)
    ctx.deps.state.nodes.append(plot)

    if fmu_node_id:
        _ensure_relation(ctx, fmu_node_id, plot.id, label=param_label or "simulate")

    result = _snapshot(ctx)
    result.return_value = {
        "job_id": job_id,
        "plot_node_id": plot.id,
        "signals": signal_names,
        "stop_time": stop_time,
    }
    return result


async def analyze_simulation_tool(
    ctx: RunContext[AgentDeps],
    job_id: str,
    question: str = "",
) -> str:
    """Analyze a simulation result visually and numerically.

    Renders the plot as an image and sends it together with sampled data
    to a vision-capable model. Returns a text analysis grounded in the plot.

    job_id: the plot_job_id from a plot canvas node.
    question: optional specific question about the result (e.g. "why does it oscillate?").
    """
    from src.fmu.service import get_result, render_plot_image, sample_data

    data = get_result(job_id)
    if data is None:
        return f"No simulation result found for job_id={job_id}."

    image_b64 = render_plot_image(data)
    csv_sample = sample_data(data)

    question_text = question.strip() or (
        "Describe the key dynamics of this simulation: trends, peaks, oscillations, "
        "steady-state behaviour, and any notable features."
    )
    prompt = (
        f"{question_text}\n\n"
        f"Sampled data (time, signals):\n{csv_sample}"
    )

    # Build OpenAI client — supports both Azure and direct OpenAI
    provider = os.getenv("DEFAULT_PROVIDER", "").lower()
    if provider == "azure" or os.getenv("AZURE_OPENAI_API_KEY"):
        from openai import AzureOpenAI
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            api_version=os.getenv("OPENAI_API_VERSION", "2024-12-01-preview"),
        )
        model = os.getenv("VISION_DEPLOYMENT") or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    else:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model = os.getenv("VISION_MODEL", "gpt-4o-mini")

    response = client.chat.completions.create(
        model=model,
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}", "detail": "low"},
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )
    return response.choices[0].message.content or "No analysis returned."
