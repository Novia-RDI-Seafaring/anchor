"""``anchor migrate`` — fold today's ~/anchor-data into the default environment.

Pre-rework, a single ``~/anchor-data`` held everything. The model now puts each
project's corpus in a hidden ``.anchor_data/`` folder, with managed (agent-made)
projects under ``~/.anchor/envs/<env>/projects/<project>/``. This command
creates the default environment (``local``) and folds the existing
``~/anchor-data`` in as its ``default`` project's ``.anchor_data/``. It is
explicit and
non-destructive: it never overwrites an existing ``default`` project, and
reports exactly what it will move.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.infra import environment as env_mod
from anchor.infra.environment import (
    DATA_DIRNAME,
    DEFAULT_PROJECT,
    create_env,
    default_env_name,
    ensure_project,
    resolve_environment,
)

migrate_app = typer.Typer(help="Fold ~/anchor-data into the default environment.")


def _has_payload(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


@migrate_app.command("bbox-origin")
def migrate_bbox_origin(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    dry_run: bool = typer.Option(False, "--dry-run", help="List legacy documents, change nothing."),
) -> None:
    """Rewrite legacy bottom-left bboxes to the canonical top-left convention (#281).

    Idempotent: documents whose pages.meta carries ``bbox_origin: top-left`` are
    skipped. ``anchor serve`` runs this automatically at startup; use it by hand
    for a project you only reach through the CLI or MCP.
    """
    import asyncio

    from anchor.adapters.cli.services import _build_real_services
    from anchor.extensions.anchor_pdfs.core.bbox_migration import (
        migrate_all,
        needs_migration,
    )

    _, _, workspace, ingest_svc, doc_store = _build_real_services(data_dir)

    async def run() -> dict:
        if dry_run:
            legacy = []
            for doc in await doc_store.list_documents():
                if needs_migration(await doc_store.get_pages_meta(doc["slug"])):
                    legacy.append(doc["slug"])
            return {"dry_run": True, "legacy_documents": legacy}
        return await migrate_all(doc_store, getattr(ingest_svc, "renderer", None), workspace)

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@migrate_app.callback(invoke_without_command=True)
def migrate(
    ctx: typer.Context,
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
    if ctx.invoked_subcommand is not None:
        return
    env_name = env or default_env_name()
    legacy = (source or env_mod.LEGACY_DATA_DIR).expanduser()
    environment = resolve_environment(env_name)
    # The default project is managed (lives under the env), with its corpus in
    # the hidden .anchor_data/ subfolder — fold the legacy tree straight in.
    default_root = environment.projects_dir / DEFAULT_PROJECT
    default_dir = default_root / DATA_DIRNAME

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
    # Drop the project marker + register the default project so it resolves by
    # name (and the cwd walk-up finds it inside its own folder).
    ensure_project(environment, DEFAULT_PROJECT)
    typer.echo("")
    typer.echo(f"Environment ready: {environment.name}")
    typer.echo(f"Projects: {environment.list_project_names() or '(none)'}")
    typer.echo(f"Point an agent at it with: anchor-mcp --env {environment.name}")
