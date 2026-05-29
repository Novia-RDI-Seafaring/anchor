"""``anchor cad`` subcommands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR, _emit_bytes

cad_app = typer.Typer(help="Inspect and parameter-tweak CAD models.")

# ── CAD subcommands ─────────────────────────────────────────────────────────
#
# Peer to the `cad.*` MCP tools. Same CadService methods that HTTP +
# MCP call.


def _build_cad_service(data_dir: Path):
    """Build a CadService with a fresh MemoryEventBus for one-shot CLI calls."""
    from anchor.extensions.anchor_cad import extension as cad_ext
    from anchor.infra.bus.memory_bus import MemoryEventBus

    return cad_ext.build_service(data_dir, MemoryEventBus())


@cad_app.command("inspect")
def cad_inspect(
    cad_path: Path = typer.Argument(...),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Upload a CAD file (STL/OBJ/STEP/glTF/JSCAD/OpenSCAD) and parse its summary."""
    if not cad_path.exists():
        typer.echo(f"CAD file not found: {cad_path}", err=True)
        raise typer.Exit(code=1)
    svc = _build_cad_service(data_dir)

    async def run():
        return await svc.upload_and_inspect(cad_path.read_bytes(), cad_path.name)

    typer.echo(asyncio.run(run()).model_dump_json(indent=2))


@cad_app.command("list")
def cad_list(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List every CAD model known to this Anchor install."""
    svc = _build_cad_service(data_dir)

    async def run():
        return [m.model_dump() for m in await svc.list_models()]

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@cad_app.command("get")
def cad_get(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Get one CAD model's summary by slug."""
    svc = _build_cad_service(data_dir)

    async def run():
        return await svc.get_model(slug)

    model = asyncio.run(run())
    if model is None:
        typer.echo(f"unknown CAD slug: {slug}", err=True)
        raise typer.Exit(code=1)
    typer.echo(model.model_dump_json(indent=2))


@cad_app.command("fetch")
def cad_fetch(
    slug: str,
    copy_to: Path | None = typer.Option(None, "--copy-to"),
    out: str | None = typer.Option(None, "--out", help="Pass '-' to stream the bytes to stdout."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print the on-disk path of the raw CAD file (or stream it with --out -)."""
    svc = _build_cad_service(data_dir)

    async def run():
        return await svc.store.get_cad_path(slug)

    path = asyncio.run(run())
    _emit_bytes(path, copy_to=copy_to, out=out, label=f"{slug} model")


@cad_app.command("set-parameter")
def cad_set_parameter(
    slug: str,
    parameter_name: str,
    value: str = typer.Argument(
        ..., help="Plain string; JSON-parsed if it looks like a number/object."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Tweak a named parameter on a parametric CAD model.

    The value is JSON-parsed when possible (so `42.5` becomes a float and
    `[1,2,3]` becomes a list). Falls back to the raw string otherwise.
    """
    parsed: object = value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        pass  # use the raw string
    svc = _build_cad_service(data_dir)

    async def run():
        return await svc.set_parameter(slug, parameter_name, parsed)

    try:
        model = asyncio.run(run())
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"failed to set parameter: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(model.model_dump_json(indent=2))
