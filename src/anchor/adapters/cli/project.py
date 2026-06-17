"""``anchor project`` — manage projects inside an Anchor environment (anchor#120).

A project owns its own documents (bronze/silver/gold) and canvases, and lives
under ``<environment>/projects/<name>/``. These commands are the CLI peers of
the ``create_project`` / ``list_projects`` MCP tools. The environment is
resolved the usual way: ``--env`` > ``ANCHOR_ENV`` > walk-up to a config file >
the global default ``~/.anchor``.
"""
from __future__ import annotations

from pathlib import Path

import typer

from anchor.core.ids import InvalidProjectNameError
from anchor.infra.environment import (
    Environment,
    create_project,
    project_meta,
    resolve_environment,
    set_project_description,
)

project_app = typer.Typer(help="Manage projects inside an Anchor environment.")


def _require_initialized(env: Environment) -> None:
    if env.initialized:
        return
    typer.echo(
        f"No Anchor environment at {env.root} (no config). "
        "Run `anchor init` here, or `anchor migrate` to adopt ~/anchor-data "
        "as the global default environment.",
        err=True,
    )
    raise typer.Exit(code=1)


@project_app.command("create")
def project_create(
    name: str = typer.Argument(..., help="Project name (becomes projects/<name>/)."),
    env: Path = typer.Option(None, "--env", help="Environment dir (default: resolved)."),
    description: str = typer.Option(
        "", "--description", help="One-line description (shown to agents in list)."
    ),
) -> None:
    """Create a project in the active environment."""
    environment = resolve_environment(env)
    _require_initialized(environment)
    try:
        create_project(environment, name, description=description)
    except InvalidProjectNameError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"Created project {name!r} at {environment.project_dir(name)}")


@project_app.command("list")
def project_list(
    env: Path = typer.Option(None, "--env", help="Environment dir (default: resolved)."),
) -> None:
    """List the projects in the active environment (name + description)."""
    environment = resolve_environment(env)
    names = environment.list_project_names()
    if not names:
        if not environment.initialized:
            typer.echo(f"No environment at {environment.root}.", err=True)
            raise typer.Exit(code=1)
        typer.echo("(no projects yet — create one with `anchor project create <name>`)")
        return
    for name in names:
        description = project_meta(environment, name).description
        typer.echo(f"{name}\t{description}" if description else name)


@project_app.command("set-description")
def project_set_description(
    name: str = typer.Argument(..., help="Project name."),
    description: str = typer.Argument(..., help="New one-line description."),
    env: Path = typer.Option(None, "--env", help="Environment dir (default: resolved)."),
) -> None:
    """Update a project's description (preserves any config overrides)."""
    environment = resolve_environment(env)
    _require_initialized(environment)
    if not environment.project_exists(name):
        typer.echo(f"Project {name!r} does not exist in {environment.root}.", err=True)
        raise typer.Exit(code=1)
    set_project_description(environment, name, description)
    typer.echo(f"Updated description for {name!r}.")
