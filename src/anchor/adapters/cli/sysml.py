"""``anchor sysml`` subcommands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.services import _build_real_services

sysml_app = typer.Typer(help="Render and export SysML v2 diagrams.")


@sysml_app.command("render")
def sysml_render(
    sysml_path: Path = typer.Argument(...),
    workspace_slug: str = typer.Option(..., "--workspace", "-w"),
    x_offset: float = typer.Option(0.0, "--x-offset"),
    y_offset: float = typer.Option(0.0, "--y-offset"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Render a .sysml file's contents onto the named workspace."""
    if not sysml_path.exists():
        typer.echo(f"SysML file not found: {sysml_path}", err=True)
        raise typer.Exit(code=1)
    _, bus, workspace, _, _ = _build_real_services(data_dir)
    from anchor.extensions.anchor_sysml import extension as sysml_ext

    svc = sysml_ext.build_service(data_dir, bus, workspace=workspace)

    async def run():
        return await svc.render(
            workspace_slug=workspace_slug,
            text=sysml_path.read_text(),
            x_offset=x_offset,
            y_offset=y_offset,
            filename=sysml_path.name,
        )

    typer.echo(json.dumps(asyncio.run(run()).model_dump(), indent=2))


@sysml_app.command("export")
def sysml_export(
    workspace_slug: str = typer.Argument(...),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Export the workspace's SysML elements back to text (Phase 1 stub)."""
    _, bus, workspace, _, _ = _build_real_services(data_dir)
    from anchor.extensions.anchor_sysml import extension as sysml_ext

    svc = sysml_ext.build_service(data_dir, bus, workspace=workspace)

    async def run():
        return await svc.export(workspace_slug=workspace_slug)

    typer.echo(asyncio.run(run()))
