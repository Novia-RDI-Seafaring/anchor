"""``anchor migrate`` — adopt today's ~/anchor-data as a #120 environment.

Pre-#120 a single ``~/anchor-data`` held everything. The two-level model puts
documents and canvases under ``<environment>/projects/<name>/``. This command
sets up the global default environment ``~/.anchor`` and moves the existing
``~/anchor-data`` in as its ``default`` project, so an agent-launched
``anchor-mcp --env ~/.anchor`` and the CLI resolve the same data. It is
explicit and non-destructive: it never overwrites an existing ``default``
project, and reports exactly what it will move.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import typer

from anchor.infra.environment import (
    DEFAULT_PROJECT,
    GLOBAL_ENV_DIR,
    LEGACY_DATA_DIR,
    ENV_CONFIG_FILENAME,
    init_environment,
    resolve_environment,
)

migrate_app = typer.Typer(help="Migrate ~/anchor-data into the ~/.anchor environment.")


def _has_payload(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


@migrate_app.callback(invoke_without_command=True)
def migrate(
    env: Path = typer.Option(
        None, "--env", help=f"Target environment (default: {GLOBAL_ENV_DIR})."
    ),
    source: Path = typer.Option(
        None, "--from", help=f"Legacy data dir to adopt (default: {LEGACY_DATA_DIR})."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not prompt."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan, change nothing."),
) -> None:
    """Set up ~/.anchor and move ~/anchor-data into it as the default project."""
    target_root = (env or GLOBAL_ENV_DIR).expanduser()
    legacy = (source or LEGACY_DATA_DIR).expanduser()
    default_dir = target_root / "projects" / DEFAULT_PROJECT
    config_path = target_root / ENV_CONFIG_FILENAME

    already_env = config_path.is_file()
    will_move = _has_payload(legacy) and not _has_payload(default_dir)

    typer.echo("Migration plan:")
    typer.echo(
        f"  environment : {target_root}"
        + ("  (already initialized)" if already_env else "  (will create anchor.toml)")
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

    if not already_env:
        init_environment(target_root)
    else:
        (target_root / "projects").mkdir(parents=True, exist_ok=True)

    if will_move:
        default_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(default_dir))
        typer.echo(f"Moved {legacy} -> {default_dir}")

    env_obj = resolve_environment(target_root)
    typer.echo("")
    typer.echo(f"Environment ready: {env_obj.root}")
    typer.echo(f"Projects: {env_obj.list_project_names() or '(none)'}")
    typer.echo("Point an agent at it with: anchor-mcp --env " + str(target_root))
