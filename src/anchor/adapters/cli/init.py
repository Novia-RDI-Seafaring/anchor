"""Initialize an Anchor project in the current working folder."""

from __future__ import annotations

from pathlib import Path

import typer

from anchor.adapters.cli.environment_setup import (
    _setup_api_key,
    create_environment,
    environment_for_project_init,
)

__all__ = ["_setup_api_key", "create_environment", "init"]


def init(
    name: str = typer.Argument(
        None, help="Project name (default: this folder's name)."
    ),
    env: str = typer.Option(
        None, "--env", help="Environment to bind this project to (default: the default env)."
    ),
    provider: str = typer.Option(
        None,
        "--provider",
        help="Provision the environment with this provider if it does not exist "
        "(local|ollama|openai|azure|custom|harness). Used only when the env is created.",
    ),
    embed_model: str = typer.Option(None, "--embed-model", help="Embedding model (with --provider)."),
    base_url: str = typer.Option(None, "--base-url", help="Endpoint (with --provider)."),
    vision_model: str = typer.Option(None, "--vision-model", help="Vision model (with --provider)."),
    docling_device: str = typer.Option(None, "--docling-device", help="cpu|cuda|mps|auto."),
    description: str = typer.Option(
        "", "--description", help="One-line description (shown to agents in the project list)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-initialize even if this folder is already a project."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept defaults, no prompts."),
) -> None:
    """Initialize an Anchor project in the current folder.

    A project is a corpus plus its canvases. This command writes an
    ``anchor.toml`` marker and a hidden ``.anchor_data`` directory, binds the
    project to an environment, and registers the project by name.
    """
    from anchor.core.ids import InvalidProjectNameError, validate_project_name
    from anchor.infra.environment import (
        PROJECT_MARKER_FILENAME,
        create_project,
        default_env_name,
    )

    folder = Path.cwd()
    project_name = name or folder.name
    try:
        validate_project_name(project_name)
    except InvalidProjectNameError as exc:
        typer.echo(
            f"{exc}\nThis folder's name is not a valid project name - pass one: "
            "`anchor init <name>`.",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    marker = folder / PROJECT_MARKER_FILENAME
    if marker.exists() and not force:
        typer.echo(
            f"This folder is already an Anchor project ({marker}).\n"
            "  - Ingest a document:        anchor ingest <pdf>\n"
            "  - Re-bind / reconfigure:    anchor init --force",
            err=True,
        )
        raise typer.Exit(code=1)

    env_name = env or default_env_name()
    environment = environment_for_project_init(
        env_name,
        provider=provider,
        embed_model=embed_model,
        base_url=base_url,
        vision_model=vision_model,
        docling_device=docling_device,
        yes=yes,
    )

    if environment.project_exists(project_name) and environment.project_root(project_name) != folder:
        typer.echo(
            f"Environment {env_name!r} already has a different project named "
            f"{project_name!r} ({environment.project_root(project_name)}). "
            "Pass a different name: `anchor init <name>`.",
            err=True,
        )
        raise typer.Exit(code=1)

    create_project(environment, project_name, root=folder, description=description)
    _report_project(environment, project_name, folder)


def _report_project(environment, project_name: str, folder: Path) -> None:
    """Report where the new project lives and what to do next."""
    from anchor.infra.environment import DATA_DIRNAME, resolve_project_config
    from anchor.infra.providers import get_provider

    config = resolve_project_config(environment, project_name)
    provider = get_provider(config.provider or "local")
    zone = provider.zone if provider else "unknown"
    typer.echo(f"Initialized project {project_name!r} in {folder}")
    typer.echo("")
    typer.echo(f"  environment : {environment.name}  ({zone})")
    typer.echo(f"  data        : {folder / DATA_DIRNAME}")
    typer.echo(f"  marker      : {folder / 'anchor.toml'}")
    typer.echo("")
    typer.echo("Next steps:")
    typer.echo("  anchor ingest <pdf>      ingest a datasheet into this project")
    typer.echo("  anchor list              see this project's documents")
    typer.echo(f"  anchor serve             open the canvas at http://localhost:{config.http_port}")
