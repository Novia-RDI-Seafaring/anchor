"""``anchor fmu`` subcommands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR

fmu_app = typer.Typer(help="Inspect and simulate FMU models.")

# ── FMU subcommands ─────────────────────────────────────────────────────────
#
# Peer to the `fmu.*` MCP tools. Each command delegates to the same
# FmuService methods used by the other adapters.


def _build_fmu_service(data_dir: Path):
    """Best-effort FMU service for one-shot CLI commands.

    Raises a clean error if neither FMPy nor the ANCHOR_FMU_DEMO=1
    opt-in is available; the FmuRuntimeUnavailableError message tells
    the user how to fix it (install the fmus extra, or set the env var
    if they want the synthetic offline demo).
    """
    try:
        from anchor.extensions.anchor_fmus import extension as fmu_ext
        from anchor.infra.bus.memory_bus import MemoryEventBus
    except ImportError as e:  # pragma: no cover
        typer.echo(f"FMU extension not available: {e}", err=True)
        raise typer.Exit(code=1) from e
    bus = MemoryEventBus()
    try:
        return fmu_ext.build_service(data_dir, bus)
    except fmu_ext.FmuRuntimeUnavailableError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@fmu_app.command("inspect")
def fmu_inspect(
    fmu_path: Path = typer.Argument(...),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Upload an .fmu and print its parsed model description."""
    if not fmu_path.exists():
        typer.echo(f"FMU not found: {fmu_path}", err=True)
        raise typer.Exit(code=1)
    svc = _build_fmu_service(data_dir)

    async def run():
        return await svc.upload_and_inspect(fmu_path.read_bytes(), fmu_path.name)

    typer.echo(asyncio.run(run()).model_dump_json(indent=2))


@fmu_app.command("list")
def fmu_list(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List every FMU known to this Anchor install."""
    svc = _build_fmu_service(data_dir)

    async def run():
        return [m.model_dump() for m in await svc.list_models()]

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@fmu_app.command("get")
def fmu_get(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Get one FMU's model description by slug."""
    svc = _build_fmu_service(data_dir)

    async def run():
        return await svc.get_model(slug)

    model = asyncio.run(run())
    if model is None:
        typer.echo(f"unknown FMU: {slug}", err=True)
        raise typer.Exit(code=1)
    typer.echo(model.model_dump_json(indent=2))


@fmu_app.command("simulate")
def fmu_simulate(
    slug: str,
    parameters: str | None = typer.Option(
        None, "--params", help="JSON object of parameter overrides."
    ),
    stop_time: float = typer.Option(1.0, "--stop-time"),
    output_interval: float = typer.Option(0.01, "--output-interval"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Run a simulation. Prints the SimulationRun JSON (includes simulation_id)."""
    overrides: dict | None = None
    if parameters is not None:
        try:
            overrides = json.loads(parameters)
        except json.JSONDecodeError as e:
            typer.echo(f"--params must be a JSON object: {e}", err=True)
            raise typer.Exit(code=2) from e
    svc = _build_fmu_service(data_dir)

    async def run():
        return await svc.simulate(
            slug,
            parameter_overrides=overrides,
            stop_time=stop_time,
            output_interval=output_interval,
        )

    typer.echo(asyncio.run(run()).model_dump_json(indent=2))


@fmu_app.command("results")
def fmu_results(
    simulation_id: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print the time series for a completed simulation."""
    svc = _build_fmu_service(data_dir)

    async def run():
        return await svc.get_series(simulation_id)

    series = asyncio.run(run())
    if series is None:
        typer.echo(f"unknown simulation: {simulation_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(series.model_dump_json(indent=2))


@fmu_app.command("simulations")
def fmu_simulations(
    fmu_slug: str | None = typer.Option(None, "--fmu", help="Filter to one FMU."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List simulation runs, optionally scoped to one FMU."""
    svc = _build_fmu_service(data_dir)

    async def run():
        return [r.model_dump() for r in await svc.list_simulations(fmu_slug)]

    typer.echo(json.dumps(asyncio.run(run()), indent=2))
