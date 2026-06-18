"""``anchor migrate`` — fold today's ~/anchor-data into the default environment.

Pre-rework, a single ``~/anchor-data`` held everything. The model now puts
documents and canvases under ``~/.anchor/envs/<env>/projects/<project>/``. This
command creates the default environment (``local``) and moves the existing
``~/anchor-data`` in as its ``default`` project. It is explicit and
non-destructive: it never overwrites an existing ``default`` project, and
reports exactly what it will move.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import typer

from anchor.infra import environment as env_mod
from anchor.infra.environment import (
    DEFAULT_PROJECT,
    create_env,
    default_env_name,
    resolve_environment,
)

migrate_app = typer.Typer(help="Fold ~/anchor-data into the default environment.")


def _has_payload(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


@migrate_app.callback(invoke_without_command=True)
def migrate(
    env: str = typer.Option(
        None, "--env", help="Target environment name (default: the default env)."
    ),
    source: Path = typer.Option(
        None, "--from", help=f"Legacy data dir to adopt (default: {env_mod.LEGACY_DATA_DIR})."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not prompt."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan, change nothing."),
) -> None:
    """Create the default environment and move ~/anchor-data into it."""
    env_name = env or default_env_name()
    legacy = (source or env_mod.LEGACY_DATA_DIR).expanduser()
    environment = resolve_environment(env_name)
    default_dir = environment.projects_dir / DEFAULT_PROJECT

    already_env = environment.initialized
    will_move = _has_payload(legacy) and not _has_payload(default_dir)

    typer.echo("Migration plan:")
    typer.echo(
        f"  environment : {env_name}  ({environment.root})"
        + ("  (exists)" if already_env else "  (will create env.toml)")
    )
    if will_move:
        typer.echo(f"  move        : {legacy}  ->  {default_dir}")
    elif _has_payload(default_dir):
        typer.echo(f"  default     : {default_dir} already has data — leaving both in place")
    elif not legacy.is_dir():
        typer.echo(f"  source      : {legacy} not found — nothing to move")
    else:
        typer.echo(f"  source      : {legacy} is empty — nothing to move")

    if dry_run:
        typer.echo("(dry run — no changes made)")
        return
    if not yes and not typer.confirm("Proceed?", default=True):
        raise typer.Exit(code=1)

    environment = create_env(env_name)

    if will_move:
        default_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(default_dir))
        typer.echo(f"Moved {legacy} -> {default_dir}")

    environment = resolve_environment(env_name)
    typer.echo("")
    typer.echo(f"Environment ready: {environment.name}")
    typer.echo(f"Projects: {environment.list_project_names() or '(none)'}")
    typer.echo(f"Point an agent at it with: anchor-mcp --env {environment.name}")
