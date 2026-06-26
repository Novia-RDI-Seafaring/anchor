"""``anchor project`` — manage projects inside an Anchor environment.

A project is a corpus (documents) plus its canvases, kept in a hidden
``.anchor_data/`` folder and registered by name in its environment's
``projects.toml``. ``anchor project create`` makes a *managed* project (its
folder lives under ``~/.anchor/envs/<env>/projects/<project>/``); ``anchor
init`` makes one in any working folder. These are the CLI peers of the
``create_project`` / ``list_projects`` / ``update_project`` /
``remove_project`` / ``rename_project`` MCP tools and the ``/api/projects``
HTTP routes. The environment is selected by name: ``--env`` > ``ANCHOR_ENV`` >
the ``anchor use`` selection > the default environment.

``anchor project move`` is the one way to cross a trust boundary, and it is
human-only on purpose (the agent must not relocate a corpus across zones).
"""
from __future__ import annotations

import typer

from anchor.core.ids import InvalidProjectNameError
from anchor.infra.environment import (
    Environment,
    ProjectNotEmptyError,
    create_project,
    move_project,
    project_meta,
    remove_project,
    rename_project,
    resolve_environment,
    set_project_description,
)
from anchor.infra.providers import get_provider

project_app = typer.Typer(
    help="Manage projects inside an Anchor environment.",
    no_args_is_help=True,
)


def _require_initialized(env: Environment) -> None:
    if env.initialized:
        return
    typer.echo(
        f"Environment {env.name!r} is not set up. Run `anchor env create {env.name}`, "
        "or `anchor migrate` to adopt ~/anchor-data.",
        err=True,
    )
    raise typer.Exit(code=1)


def _zone_of(env: Environment) -> str:
    from anchor.infra.environment import DEFAULT_PROJECT, resolve_project_config

    cfg = resolve_project_config(env, DEFAULT_PROJECT)
    prov = get_provider(cfg.provider or "local")
    return prov.zone if prov else "unknown"


@project_app.command("create")
def project_create(
    name: str = typer.Argument(..., help="Project name (managed at projects/<name>/)."),
    env: str = typer.Option(None, "--env", help="Environment name (default: resolved)."),
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
    typer.echo(f"Created project {name!r} in environment {environment.name!r}")
    typer.echo(f"  {environment.project_dir(name)}")


@project_app.command("list")
def project_list(
    env: str = typer.Option(None, "--env", help="Environment name (default: resolved)."),
) -> None:
    """List the projects in the active environment (name + description)."""
    environment = resolve_environment(env)
    names = environment.list_project_names()
    if not names:
        if not environment.initialized:
            typer.echo(f"Environment {environment.name!r} is not set up.", err=True)
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
    env: str = typer.Option(None, "--env", help="Environment name (default: resolved)."),
) -> None:
    """Update a project's description (preserves any config overrides)."""
    environment = resolve_environment(env)
    _require_initialized(environment)
    if not environment.project_exists(name):
        typer.echo(f"Project {name!r} does not exist in {environment.name!r}.", err=True)
        raise typer.Exit(code=1)
    set_project_description(environment, name, description)
    typer.echo(f"Updated description for {name!r}.")


@project_app.command("move")
def project_move(
    name: str = typer.Argument(..., help="Project to move."),
    to: str = typer.Option(..., "--to", help="Destination environment name."),
    env: str = typer.Option(None, "--env", help="Source environment name (default: resolved)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the zone-change confirmation."),
) -> None:
    """Move a project to another environment (a deliberate, zone-aware move).

    Crossing a trust boundary changes where the corpus may go, so this confirms
    the egress zone change before relocating the data.
    """
    source = resolve_environment(env)
    dest = resolve_environment(to)
    _require_initialized(source)
    _require_initialized(dest)
    if not source.project_exists(name):
        typer.echo(f"Project {name!r} does not exist in {source.name!r}.", err=True)
        raise typer.Exit(code=1)

    from_zone = _zone_of(source)
    to_zone = _zone_of(dest)
    typer.echo(f"Move {name!r}: {source.name} ({from_zone})  ->  {dest.name} ({to_zone})")
    if from_zone != to_zone and not yes:
        if not typer.confirm(
            f"This changes the data zone from '{from_zone}' to '{to_zone}'. Proceed?",
            default=False,
        ):
            raise typer.Exit(code=1)
    try:
        move_project(source, name, dest)
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Moved {name!r} to {dest.name!r}: {dest.project_dir(name)}")


@project_app.command("remove")
def project_remove(
    name: str = typer.Argument(..., help="Project to remove."),
    env: str = typer.Option(None, "--env", help="Environment name (default: resolved)."),
    delete_data: bool = typer.Option(
        False, "--delete-data", help="Also delete the project's .anchor_data/ + anchor.toml."
    ),
    force: bool = typer.Option(
        False, "--force", help="Remove even when the project still has documents/canvases."
    ),
) -> None:
    """Deregister a project (optionally deleting its data). Never touches others.

    By default this only deregisters the project from the environment's
    ``projects.toml`` and refuses a project that still has documents or
    canvases. Pass ``--force`` to remove a non-empty project and ``--delete-data``
    to also remove its on-disk ``.anchor_data/`` folder and ``anchor.toml`` marker.
    """
    environment = resolve_environment(env)
    _require_initialized(environment)
    if not environment.project_exists(name):
        typer.echo(f"Project {name!r} does not exist in {environment.name!r}.", err=True)
        raise typer.Exit(code=1)
    try:
        result = remove_project(
            environment, name, delete_data=delete_data, force=force
        )
    except ProjectNotEmptyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if result["deleted_data"]:
        typer.echo(f"Removed project {name!r} from {environment.name!r} (data deleted).")
    else:
        typer.echo(f"Removed project {name!r} from {environment.name!r}.")


@project_app.command("rename")
def project_rename(
    old: str = typer.Argument(..., help="Current project name."),
    new: str = typer.Argument(..., help="New project name."),
    env: str = typer.Option(None, "--env", help="Environment name (default: resolved)."),
) -> None:
    """Rename a project (registry + anchor.toml). The folder path is unchanged."""
    environment = resolve_environment(env)
    _require_initialized(environment)
    if not environment.project_exists(old):
        typer.echo(f"Project {old!r} does not exist in {environment.name!r}.", err=True)
        raise typer.Exit(code=1)
    try:
        rename_project(environment, old, new)
    except InvalidProjectNameError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from exc
    except FileExistsError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Renamed {old!r} to {new!r} in {environment.name!r}.")
