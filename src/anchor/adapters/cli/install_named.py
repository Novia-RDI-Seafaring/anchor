"""Collision-safe installers for named Codex and OpenCode MCP entries."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from anchor.adapters.cli.install_config_io import (
    load_json,
    load_toml,
    write_codex_toml,
    write_json,
)


def _codex_config_path() -> Path:
    base = os.environ.get("CODEX_HOME")
    root = Path(base) if base else Path.home() / ".codex"
    return root / "config.toml"


def _opencode_config_path() -> Path:
    custom = os.environ.get("OPENCODE_CONFIG")
    if custom:
        return Path(custom).expanduser()
    return Path.home() / ".config" / "opencode" / "opencode.json"


def _anchor_command(env_name: str) -> list[str]:
    executable = shutil.which("anchor-mcp") or str(Path(sys.executable).parent / "anchor-mcp")
    return [executable, "--env", env_name]


def _selection(
    *,
    env: str | None,
    name: str | None,
    create: bool,
    dry_run: bool,
) -> tuple[str, str, bool, str]:
    from anchor.infra.environment import (
        DEFAULT_PROJECT,
        create_env,
        default_env_name,
        resolve_environment,
        resolve_project_config,
    )
    from anchor.infra.providers import get_provider

    env_name = env or default_env_name()
    entry_name = name or f"anchor-{env_name}"
    if create and not dry_run:
        create_env(env_name)

    environment = resolve_environment(env_name)
    if not environment.initialized:
        return env_name, entry_name, False, "not set up yet (the agent will create it)"
    config = resolve_project_config(environment, DEFAULT_PROJECT)
    provider = get_provider(config.provider or "local")
    return env_name, entry_name, True, provider.zone if provider else "unknown"


def _confirm_and_report(
    *,
    harness: str,
    env_name: str,
    entry_name: str,
    initialized: bool,
    zone: str,
    yes: bool,
    dry_run: bool,
) -> None:
    typer.echo(f"Environment : {env_name}")
    typer.echo(f"Data zone   : {zone}")
    if dry_run or yes:
        return
    if not typer.confirm(
        f"Wire {harness} MCP server '{entry_name}' for environment '{env_name}'?",
        default=initialized,
    ):
        raise typer.Exit(code=1)


def _refuse_collision(
    *,
    entry_name: str,
    existing: dict[str, Any] | None,
    desired_command: list[str],
    command_of: Callable[[dict[str, Any]], list[str] | None],
    force: bool,
) -> None:
    existing_command = command_of(existing) if existing is not None else None
    if existing is None or existing_command == desired_command or force:
        return
    typer.echo(
        f"MCP server '{entry_name}' already points at {existing_command}. "
        "Use --name <other> to add another environment, or --force to repoint.",
        err=True,
    )
    raise typer.Exit(code=1)


def install_codex(
    env: str = typer.Option(None, "--env", help="Environment NAME (default: default env)."),
    name: str = typer.Option(None, "--name", help="MCP entry name (default: anchor-<env>)."),
    create: bool = typer.Option(False, "--create", help="Create the environment now."),
    force: bool = typer.Option(False, "--force", help="Repoint an existing entry."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip egress-zone confirmation."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register an Anchor environment as a named MCP server in Codex."""
    env_name, entry_name, initialized, zone = _selection(
        env=env, name=name, create=create, dry_run=dry_run
    )
    path = _codex_config_path()
    config = load_toml(path)
    servers = config.setdefault("mcp_servers", {})
    command = _anchor_command(env_name)
    desired = {"command": command[0], "args": command[1:]}
    _refuse_collision(
        entry_name=entry_name,
        existing=servers.get(entry_name),
        desired_command=command,
        command_of=lambda item: [item.get("command"), *item.get("args", [])],
        force=force,
    )
    _confirm_and_report(
        harness="Codex",
        env_name=env_name,
        entry_name=entry_name,
        initialized=initialized,
        zone=zone,
        yes=yes,
        dry_run=dry_run,
    )
    servers[entry_name] = desired
    if not dry_run:
        write_codex_toml(path, config)
    _report_result("Codex", entry_name, path, command, dry_run=dry_run)


def install_opencode(
    env: str = typer.Option(None, "--env", help="Environment NAME (default: default env)."),
    name: str = typer.Option(None, "--name", help="MCP entry name (default: anchor-<env>)."),
    create: bool = typer.Option(False, "--create", help="Create the environment now."),
    force: bool = typer.Option(False, "--force", help="Repoint an existing entry."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip egress-zone confirmation."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register an Anchor environment as a named local MCP server in OpenCode."""
    env_name, entry_name, initialized, zone = _selection(
        env=env, name=name, create=create, dry_run=dry_run
    )
    path = _opencode_config_path()
    config = load_json(path)
    config.setdefault("$schema", "https://opencode.ai/config.json")
    servers = config.setdefault("mcp", {})
    command = _anchor_command(env_name)
    desired = {"type": "local", "command": command, "enabled": True}
    _refuse_collision(
        entry_name=entry_name,
        existing=servers.get(entry_name),
        desired_command=command,
        command_of=lambda item: item.get("command"),
        force=force,
    )
    _confirm_and_report(
        harness="OpenCode",
        env_name=env_name,
        entry_name=entry_name,
        initialized=initialized,
        zone=zone,
        yes=yes,
        dry_run=dry_run,
    )
    servers[entry_name] = desired
    if not dry_run:
        write_json(path, config)
    _report_result("OpenCode", entry_name, path, command, dry_run=dry_run)


def _report_result(
    harness: str,
    entry_name: str,
    path: Path,
    command: list[str],
    *,
    dry_run: bool,
) -> None:
    prefix = "[dry-run] " if dry_run else ""
    typer.echo(prefix + f"MCP entry '{entry_name}' -> {path}")
    typer.echo(f"          command: {command}")
    if not dry_run:
        typer.echo("")
        typer.echo("Next:")
        typer.echo(f"  1. Run `{harness.lower()} mcp list` to verify the server.")
        typer.echo("  2. Ask the agent to list Anchor projects, then select one by name.")
