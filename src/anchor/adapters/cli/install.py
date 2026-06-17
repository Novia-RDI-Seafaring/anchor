"""`anchor install <target>` — register Anchor with an AI harness.

This command does not install the ANCHOR tool itself. Install the tool with
`uv tool install anchor-kb` first.

Targets:
    claude-code   Add MCP server entry to ~/.claude.json (the file Claude
                  Code actually reads) and write a skill file at
                  ~/.claude/skills/anchor/SKILL.md so Claude Code knows when
                  to use Anchor's tools.
    cursor        Add MCP server entry to ~/.cursor/mcp.json.
    print         Print what would be installed without writing anything.

Idempotent: existing entries are updated in place; re-running is safe.
The `--data-dir` becomes the default path the MCP server points at — you
can change it later by editing the config or by re-running `anchor install`.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import typer

from anchor.adapters.cli.common import default_data_dir
from anchor.adapters.skills import compose_skill_md, discover_third_party_manifests

install_app = typer.Typer(
    help=(
        "Register Anchor with an AI harness. "
        "To install the tool itself, run `uv tool install anchor-kb`."
    )
)


# ── target descriptions ────────────────────────────────────────────────


def _claude_code_paths() -> tuple[Path, Path]:
    # MCP servers for Claude Code live in ~/.claude.json (the dotfile in
    # $HOME), NOT ~/.claude/mcp.json, which Claude Code never reads. Writing
    # to the latter silently registers nothing. Skills do live under
    # ~/.claude/skills/, so only the MCP path moves.
    home = Path.home()
    return (home / ".claude.json", home / ".claude" / "skills" / "anchor")


def _cursor_paths() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def _claude_desktop_config_path() -> Path:
    """The claude_desktop_config.json location for the current platform."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        root = Path(base) if base else home / "AppData" / "Roaming"
        return root / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"



# ── installer impl ─────────────────────────────────────────────────────


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return json.loads(text)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # ~/.claude.json also holds unrelated Claude Code state, so guard the
    # write: back the file up once before the first overwrite, and write
    # atomically (temp + os.replace) so a crash mid-write cannot truncate it.
    if path.exists():
        backup = path.parent / (path.name + ".anchorbak")
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _resolve_anchor_mcp() -> str:
    """Find the `anchor-mcp` binary or return the script path."""
    on_path = shutil.which("anchor-mcp")
    if on_path:
        return on_path
    # Fallback: the current Python's bin dir
    return str(Path(sys.executable).parent / "anchor-mcp")


def _build_mcp_entry(data_dir: Path, *, pin: bool = False) -> dict[str, Any]:
    # Default to a folder-resolving entry (no baked --data-dir). The server
    # resolves the project from its working directory — the folder the agent is
    # launched in — so a single registration serves every `anchor init` project
    # with no per-project reinstall. Pass pin=True (an explicit --data-dir) to
    # hard-wire one project's data dir instead.
    entry: dict[str, Any] = {"command": _resolve_anchor_mcp(), "args": []}
    if pin:
        entry["args"] = ["--data-dir", str(data_dir.resolve())]
    return entry


def _install_mcp(
    config_path: Path, data_dir: Path, *, pin: bool, dry_run: bool
) -> tuple[Path, dict[str, Any]]:
    cfg = _load_json(config_path)
    cfg.setdefault("mcpServers", {})
    cfg["mcpServers"]["anchor"] = _build_mcp_entry(data_dir, pin=pin)
    if not dry_run:
        _write_json(config_path, cfg)
    return config_path, cfg["mcpServers"]["anchor"]


def _install_skill(skill_dir: Path, data_dir: Path, *, dry_run: bool) -> Path:
    """Write the composed SKILL.md to ``skill_dir``.

    Sources:

    - bundled skill files under ``src/anchor/skills/`` shipped as
      package data
    - third-party OIP producer manifests discovered via the standard
      OIP locations (system-wide ``$XDG_CONFIG_HOME/oip/producers.d/``
      and the active data dir's ``.oip/producers.d/``)

    See ``anchor.adapters.skills`` for the composition rules.
    """
    skill_path = skill_dir / "SKILL.md"
    if not dry_run:
        skill_dir.mkdir(parents=True, exist_ok=True)
        third_party = discover_third_party_manifests(data_dir=data_dir)
        skill_path.write_text(
            compose_skill_md(third_party_manifests=third_party),
            encoding="utf-8",
        )
    return skill_path


# ── CLI commands ───────────────────────────────────────────────────────


@install_app.command("claude-code")
def install_claude_code(
    data_dir: Path = typer.Option(
        None,
        "--data-dir",
        "-d",
        help="Pin one project's data dir. Omit (default) to register a "
        "folder-resolving entry that works for every `anchor init` project "
        "— no reinstall when you switch projects.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register Anchor as MCP server + skill in Claude Code."""
    pin = data_dir is not None
    if data_dir is None:
        data_dir = default_data_dir()
    mcp_config_path, skill_dir = _claude_code_paths()
    config_path, entry = _install_mcp(mcp_config_path, data_dir, pin=pin, dry_run=dry_run)
    skill_path = _install_skill(skill_dir, data_dir, dry_run=dry_run)
    if not dry_run and pin and not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(("[dry-run] " if dry_run else "") + f"MCP entry -> {config_path}")
    typer.echo(f"          command: {entry['command']}")
    typer.echo(f"          args:    {entry['args']}")
    typer.echo(("[dry-run] " if dry_run else "") + f"Skill    -> {skill_path}")
    if pin:
        typer.echo(("[dry-run] " if dry_run else "") + f"Data dir -> {data_dir} (pinned)")
    else:
        typer.echo("Data dir -> resolved per project from the folder you run Claude Code in")
        typer.echo("           (run `anchor init` in a project, then start Claude Code there)")
    if not dry_run:
        typer.echo("")
        typer.echo("Next:")
        typer.echo("  1. Restart Claude Code (the MCP server list reloads on startup).")
        typer.echo("  2. /mcp in Claude Code should list 'anchor' with its available tools.")
        typer.echo("  3. Try: 'list anchor documents' or 'ingest this PDF: <path>'.")


@install_app.command("cursor")
def install_cursor(
    data_dir: Path = typer.Option(
        None,
        "--data-dir",
        "-d",
        help="Pin one project's data dir. Omit (default) to register a "
        "folder-resolving entry that works for every `anchor init` project.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register Anchor as MCP server in Cursor."""
    pin = data_dir is not None
    if data_dir is None:
        data_dir = default_data_dir()
    config_path, entry = _install_mcp(_cursor_paths(), data_dir, pin=pin, dry_run=dry_run)
    if not dry_run and pin and not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(("[dry-run] " if dry_run else "") + f"MCP entry -> {config_path}")
    typer.echo(f"          command: {entry['command']}")
    typer.echo(f"          args:    {entry['args']}")
    if pin:
        typer.echo(("[dry-run] " if dry_run else "") + f"Data dir -> {data_dir} (pinned)")
    else:
        typer.echo("Data dir -> resolved per project from the folder Cursor runs the server in")


def _env_pointer_entry(env_dir: Path) -> dict[str, Any]:
    """A pointer MCP entry: the server resolves settings from the env config."""
    return {"command": _resolve_anchor_mcp(), "args": ["--env", str(env_dir)]}


def _environment_zone(env_dir: Path) -> tuple[bool, str]:
    """Return (initialized, egress-zone label) for an environment directory."""
    from anchor.infra.environment import DEFAULT_PROJECT, resolve_environment, resolve_project_config
    from anchor.infra.providers import get_provider

    env = resolve_environment(env_dir)
    if not env.initialized:
        return False, "not set up yet (the agent will create it on first use)"
    cfg = resolve_project_config(env, DEFAULT_PROJECT)
    provider = get_provider(cfg.provider or "local")
    return True, provider.zone if provider else "unknown"


@install_app.command("claude-desktop")
def install_claude_desktop(
    env: Path = typer.Option(
        None, "--env", help="Environment to point at (default: ~/.anchor)."
    ),
    name: str = typer.Option(
        "anchor", "--name", help="MCP server entry name (use a distinct name per environment)."
    ),
    create: bool = typer.Option(
        False, "--create", help="Initialize the environment now instead of on first use."
    ),
    force: bool = typer.Option(
        False, "--force", help="Repoint an existing entry of this name at a different environment."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the egress-zone confirmation."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register an Anchor environment as a named MCP server in Claude Desktop.

    The entry is a pointer (``anchor-mcp --env <dir>``): settings live in the
    environment's config, so the CLI and MCP always resolve the same thing.
    Additive and collision-safe — other servers are preserved, and an existing
    name pointing at a different environment is refused (pass ``--name`` to add
    a second, or ``--force`` to repoint).
    """
    from anchor.infra.environment import GLOBAL_ENV_DIR, init_environment

    env_dir = (env or GLOBAL_ENV_DIR).expanduser()
    if create and not dry_run:
        init_environment(env_dir)

    config_path = _claude_desktop_config_path()
    cfg = _load_json(config_path)
    servers = cfg.setdefault("mcpServers", {})

    existing = servers.get(name)
    desired = _env_pointer_entry(env_dir)
    if existing is not None and existing.get("args") != desired["args"] and not force:
        typer.echo(
            f"MCP server '{name}' already points at {existing.get('args')}. "
            f"Use --name <other> to add a second environment, or --force to repoint.",
            err=True,
        )
        raise typer.Exit(code=1)

    initialized, zone = _environment_zone(env_dir)
    typer.echo(f"Environment: {env_dir}")
    typer.echo(f"Egress zone: {zone}")
    if not dry_run and not yes:
        if not typer.confirm(
            f"Documents in this environment may be sent to: {zone}. "
            f"Add MCP server '{name}'?",
            default=initialized,
        ):
            raise typer.Exit(code=1)

    servers[name] = desired
    if not dry_run:
        _write_json(config_path, cfg)

    typer.echo(("[dry-run] " if dry_run else "") + f"MCP entry '{name}' -> {config_path}")
    typer.echo(f"          command: {desired['command']}")
    typer.echo(f"          args:    {desired['args']}")
    if not dry_run:
        typer.echo("")
        typer.echo("Next:")
        typer.echo("  1. Restart Claude Desktop (the MCP server list reloads on startup).")
        typer.echo("  2. Ask it to create a project: 'make an Anchor project for my pumps'.")
        typer.echo("  3. Then ingest a PDF and build a canvas — all in chat, no terminal.")


@install_app.command("print")
def install_print(
    data_dir: Path = typer.Option(None, "--data-dir", "-d"),
) -> None:
    """Print the install plan for every supported target without writing."""
    # Pass data_dir through unchanged (None when not given) so each target
    # reflects the real default — a folder-resolving entry, not a pinned one.
    typer.echo("=== claude-code ===")
    install_claude_code(data_dir=data_dir, dry_run=True)
    typer.echo("")
    typer.echo("=== claude-desktop ===")
    install_claude_desktop(
        env=None, name="anchor", create=False, force=False, yes=True, dry_run=True
    )
    typer.echo("")
    typer.echo("=== cursor ===")
    install_cursor(data_dir=data_dir, dry_run=True)
