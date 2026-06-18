"""``anchor env`` — manage environments (named configuration profiles).

An environment is a reusable profile (provider / models / data **zone**) and
the trust boundary that holds projects. Environments live under
``~/.anchor/envs/<name>/``. ``anchor env create`` is the provider picker (same
as ``anchor init``); ``anchor env list`` / ``show`` / ``default`` manage the
set. ``anchor use`` sets a session default so later commands can omit
``--env`` / ``--project``.
"""
from __future__ import annotations

import typer

from anchor.infra.environment import (
    DEFAULT_PROJECT,
    default_env_name,
    environment_meta,
    list_env_names,
    project_meta,
    resolve_environment,
    resolve_project_config,
    set_default_env,
    set_use,
)
from anchor.infra.providers import get_provider

env_app = typer.Typer(help="Manage Anchor environments (named config profiles).")


def _zone(env_name: str) -> str:
    env = resolve_environment(env_name)
    if not env.initialized:
        return "not set up"
    cfg = resolve_project_config(env, DEFAULT_PROJECT)
    prov = get_provider(cfg.provider or "local")
    return prov.zone if prov else "unknown"


@env_app.command("create")
def env_create(
    name: str = typer.Argument(..., help="Environment name to create."),
    provider: str = typer.Option(None, "--provider", help="local|ollama|openai|azure|custom."),
    embed_model: str = typer.Option(None, "--embed-model", help="Local embedding model id."),
    base_url: str = typer.Option(None, "--base-url", help="Endpoint for the chosen provider."),
    vision_model: str = typer.Option(None, "--vision-model", help="Polish + region model/deployment."),
    docling_device: str = typer.Option(None, "--docling-device", help="cpu|cuda|mps|auto."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept defaults, no prompts."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing environment."),
) -> None:
    """Create an environment (provider / data-zone) and its default project.

    Identical to ``anchor init <name>`` — both create the named environment and
    scaffold its ``default`` project.
    """
    from anchor.adapters.cli.init import init as init_cmd

    init_cmd(
        name=name,
        provider=provider,
        embed_model=embed_model,
        base_url=base_url,
        vision_model=vision_model,
        docling_device=docling_device,
        yes=yes,
        force=force,
    )


@env_app.command("list")
def env_list() -> None:
    """List the environments on this system (name, zone, description)."""
    names = list_env_names()
    default = default_env_name()
    if not names:
        typer.echo("(no environments yet — create one with `anchor init` or `anchor env create`)")
        return
    for name in names:
        marker = " *" if name == default else "  "
        desc = environment_meta(resolve_environment(name)).description
        line = f"{marker} {name}\t{_zone(name)}"
        if desc:
            line += f"\t{desc}"
        typer.echo(line)
    typer.echo("")
    typer.echo("(* = default environment)")


@env_app.command("show")
def env_show(
    name: str = typer.Argument(None, help="Environment name (default: the default env)."),
) -> None:
    """Show an environment's profile and its projects."""
    env = resolve_environment(name)
    if not env.initialized:
        typer.echo(f"Environment {env.name!r} is not set up.", err=True)
        raise typer.Exit(code=1)
    cfg = resolve_project_config(env, DEFAULT_PROJECT)
    typer.echo(f"environment : {env.name}")
    typer.echo(f"profile     : {env.config_path}")
    typer.echo(f"zone        : {_zone(env.name)}")
    typer.echo(f"embed model : {cfg.embed_model}")
    if cfg.openai_base_url:
        typer.echo(f"endpoint    : {cfg.openai_base_url}")
    typer.echo("projects    :")
    names = env.list_project_names()
    if not names:
        typer.echo("  (none yet)")
    for project in names:
        desc = project_meta(env, project).description
        typer.echo(f"  {project}\t{desc}" if desc else f"  {project}")


@env_app.command("default")
def env_default(
    name: str = typer.Argument(..., help="Environment to make the default."),
) -> None:
    """Set the default environment (used when a command omits --env)."""
    env = resolve_environment(name)
    if not env.initialized:
        typer.echo(f"Environment {name!r} is not set up.", err=True)
        raise typer.Exit(code=1)
    set_default_env(name)
    typer.echo(f"Default environment is now {name!r}.")


def use(
    env: str = typer.Argument(..., help="Environment to select for this CLI session."),
    project: str = typer.Argument(None, help="Optional project to select too."),
) -> None:
    """Set a session default env (and optionally project) so later CLI commands
    can omit --env / --project. Does not affect the agent (MCP) path."""
    environment = resolve_environment(env)
    if not environment.initialized:
        typer.echo(f"Environment {env!r} is not set up.", err=True)
        raise typer.Exit(code=1)
    if project is not None and not environment.project_exists(project):
        typer.echo(f"Project {project!r} does not exist in {env!r}.", err=True)
        raise typer.Exit(code=1)
    set_use(env, project)
    sel = f"{env}" + (f" / {project}" if project else "")
    typer.echo(f"Using {sel} for this session.")
