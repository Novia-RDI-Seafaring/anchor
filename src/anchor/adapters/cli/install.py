"""`anchor install <target>` — register Anchor with an AI harness.

This command does not install the ANCHOR tool itself. Install the tool with
`uv tool install anchor-kb` first.

Targets:
    claude-code   Add MCP server entry to ~/.claude.json (the file Claude
                  Code actually reads) and write a skill file at
                  ~/.claude/skills/anchor/SKILL.md so Claude Code knows when
                  to use Anchor's tools.
    cursor        Add MCP server entry to ~/.cursor/mcp.json. Pass --rules to
                  also write a project-scoped .cursor/rules/anchor.mdc that
                  points a Cursor agent in this workspace at AGENTS.md + the
                  anchor CLI/MCP surfaces.
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


def _cursor_rules_path(project_dir: Path) -> Path:
    """Project-scoped Cursor rules file for the Anchor briefing.

    Cursor has no global skills directory; it reads project-scoped
    ``.cursor/rules/*.mdc`` (and ``AGENTS.md``). This is the per-project
    pointer that makes a Cursor agent auto-load the Anchor briefing.
    """
    return project_dir / ".cursor" / "rules" / "anchor.mdc"


# The rules file is a short pointer, not a copy of AGENTS.md. It tells a
# Cursor agent where the single source of truth lives and how Anchor is
# reachable, so the briefing stays in one place. ASCII only, no em-dashes:
# Cursor reads this on a fresh workspace and a cp1252 write would corrupt it.
_CURSOR_RULES_MDC = """\
---
description: Anchor workspace briefing (auto-loaded by Cursor)
alwaysApply: true
---

# Anchor project

This workspace is an Anchor project. Anchor is an agent-native canvas for
turning engineering PDFs into source-grounded knowledge and wiring it onto a
canvas.

- Read `AGENTS.md` at the project root first. It is the vendor-neutral
  briefing (conventions, architecture, the bronze/silver/gold ingestion
  pipeline). Do not duplicate it here; it is the single source of truth.
- Anchor is reachable two ways, with parity:
  - the `anchor` CLI (run `anchor --help`; e.g. `anchor ingest <pdf>`,
    `anchor canvas list`),
  - the `anchor` MCP server, which injects its own tool briefing on connect.
- Treat this Cursor workspace as one Anchor project. Ingest, query, and place
  nodes through the CLI or MCP tools; do not write your own PDF/OCR parsing.
"""


def _install_cursor_rules(project_dir: Path, *, force: bool, dry_run: bool) -> tuple[Path, bool]:
    """Write the project-scoped ``.cursor/rules/anchor.mdc`` pointer.

    Idempotent and edit-safe: writes only when the file is absent or its
    content differs from the shipped pointer, and never overwrites a
    user-edited file unless ``force`` is passed. Returns ``(path, wrote)``.
    """
    rules_path = _cursor_rules_path(project_dir)
    existing = rules_path.read_text(encoding="utf-8") if rules_path.exists() else None
    up_to_date = existing == _CURSOR_RULES_MDC
    user_edited = existing is not None and not up_to_date
    if up_to_date or (user_edited and not force):
        return rules_path, False
    if not dry_run:
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_text(_CURSOR_RULES_MDC, encoding="utf-8")
    return rules_path, True


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


def _install_env_pointer(config_path: Path, env_name: str, *, dry_run: bool) -> dict[str, Any]:
    """Write/replace the single ``anchor`` MCP entry pointing at ``env_name``."""
    cfg = _load_json(config_path)
    cfg.setdefault("mcpServers", {})["anchor"] = _env_pointer_entry(env_name)
    if not dry_run:
        _write_json(config_path, cfg)
    return cfg["mcpServers"]["anchor"]


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


def _default_env_name() -> str:
    from anchor.infra.environment import default_env_name

    return default_env_name()


def _env_skill_data_dir(env_name: str) -> Path:
    from anchor.infra.environment import DEFAULT_PROJECT, resolve_environment

    return resolve_environment(env_name).project_dir(DEFAULT_PROJECT)


@install_app.command("claude-code")
def install_claude_code(
    env: str = typer.Option(
        None, "--env", help="Environment NAME the server serves (default: the default env)."
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register Anchor as MCP server + skill in Claude Code."""
    env_name = env or _default_env_name()
    mcp_config_path, skill_dir = _claude_code_paths()
    entry = _install_env_pointer(mcp_config_path, env_name, dry_run=dry_run)
    skill_path = _install_skill(skill_dir, _env_skill_data_dir(env_name), dry_run=dry_run)

    typer.echo(("[dry-run] " if dry_run else "") + f"MCP entry 'anchor' -> {mcp_config_path}")
    typer.echo(f"          command: {entry['command']}")
    typer.echo(f"          args:    {entry['args']}")
    typer.echo(("[dry-run] " if dry_run else "") + f"Skill    -> {skill_path}")
    if not dry_run:
        typer.echo("")
        typer.echo("Next:")
        typer.echo("  1. Restart Claude Code (the MCP server list reloads on startup).")
        typer.echo("  2. /mcp in Claude Code should list 'anchor' with its available tools.")
        typer.echo("  3. Try: 'list anchor projects' or 'create a project for my pumps'.")


@install_app.command("cursor")
def install_cursor(
    env: str = typer.Option(
        None, "--env", help="Environment NAME the server serves (default: the default env)."
    ),
    rules: bool = typer.Option(
        False,
        "--rules",
        help="Also write a project-scoped .cursor/rules/anchor.mdc pointing this "
        "Cursor workspace at AGENTS.md + the anchor CLI/MCP surfaces.",
    ),
    project_dir: Path = typer.Option(
        None,
        "--project-dir",
        help="Project directory for --rules (default: the current directory).",
    ),
    force: bool = typer.Option(
        False, "--force", help="With --rules, overwrite a user-edited anchor.mdc."
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register Anchor as MCP server in Cursor.

    With ``--rules``, also writes a project-scoped ``.cursor/rules/anchor.mdc``
    so a Cursor agent opened in this workspace auto-loads the Anchor briefing
    (it points at ``AGENTS.md`` + the CLI/MCP surfaces, it does not duplicate
    them). The rules write is idempotent and will not clobber a user-edited
    file unless ``--force`` is passed.
    """
    env_name = env or _default_env_name()
    config_path = _cursor_paths()
    entry = _install_env_pointer(config_path, env_name, dry_run=dry_run)
    typer.echo(("[dry-run] " if dry_run else "") + f"MCP entry 'anchor' -> {config_path}")
    typer.echo(f"          command: {entry['command']}")
    typer.echo(f"          args:    {entry['args']}")
    if rules:
        target = (project_dir or Path.cwd()).resolve()
        rules_path, wrote = _install_cursor_rules(target, force=force, dry_run=dry_run)
        prefix = "[dry-run] " if dry_run else ""
        if wrote:
            typer.echo(prefix + f"Rules    -> {rules_path}")
        else:
            typer.echo(f"Rules    -> {rules_path} (up to date; pass --force to overwrite)")


def _env_pointer_entry(env_name: str) -> dict[str, Any]:
    """A pointer MCP entry: the server resolves settings from the env profile."""
    return {"command": _resolve_anchor_mcp(), "args": ["--env", env_name]}


def _environment_zone(env_name: str) -> tuple[bool, str]:
    """Return (initialized, egress-zone label) for an environment name."""
    from anchor.infra.environment import (
        DEFAULT_PROJECT,
        resolve_environment,
        resolve_project_config,
    )
    from anchor.infra.providers import get_provider

    env = resolve_environment(env_name)
    if not env.initialized:
        return False, "not set up yet (the agent will create it on first use)"
    cfg = resolve_project_config(env, DEFAULT_PROJECT)
    provider = get_provider(cfg.provider or "local")
    return True, provider.zone if provider else "unknown"


@install_app.command("claude-desktop")
def install_claude_desktop(
    env: str = typer.Option(
        None, "--env", help="Environment NAME to point at (default: the default env)."
    ),
    name: str = typer.Option(
        None,
        "--name",
        help="MCP server entry name (default: 'anchor-<env>', so the name tells you "
        "which environment it is and multiple environments never collide).",
    ),
    create: bool = typer.Option(
        False, "--create", help="Create the environment now instead of on first use."
    ),
    force: bool = typer.Option(
        False, "--force", help="Repoint an existing entry of this name at a different environment."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the egress-zone confirmation."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register an Anchor environment as a named MCP server in Claude Desktop.

    The entry is a pointer (``anchor-mcp --env <name>``): settings live in the
    environment's profile, so the CLI and MCP always resolve the same thing.
    Additive and collision-safe — other servers are preserved, and an existing
    name pointing at a different environment is refused (pass ``--name`` to add
    a second, or ``--force`` to repoint).
    """
    from anchor.infra.environment import create_env, default_env_name

    env_name = env or default_env_name()
    if name is None:
        # 'anchor-<env>' so the entry name tells you which environment it is and
        # wiring one server per environment never collides on the config key.
        name = f"anchor-{env_name}"
    if create and not dry_run:
        create_env(env_name)

    config_path = _claude_desktop_config_path()
    cfg = _load_json(config_path)
    servers = cfg.setdefault("mcpServers", {})

    existing = servers.get(name)
    desired = _env_pointer_entry(env_name)
    if existing is not None and existing.get("args") != desired["args"] and not force:
        typer.echo(
            f"MCP server '{name}' already points at {existing.get('args')}. "
            f"Use --name <other> to add a second environment, or --force to repoint.",
            err=True,
        )
        raise typer.Exit(code=1)

    initialized, zone = _environment_zone(env_name)
    typer.echo(f"Environment : {env_name}")
    typer.echo(f"Data zone   : {zone}")
    if not dry_run and not yes:
        if not typer.confirm(
            f"Wire MCP server '{name}' for environment '{env_name}'?",
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
    env: str = typer.Option(None, "--env", help="Environment NAME (default: the default env)."),
) -> None:
    """Print the install plan for every supported target without writing."""
    typer.echo("=== claude-code ===")
    install_claude_code(env=env, dry_run=True)
    typer.echo("")
    typer.echo("=== claude-desktop ===")
    install_claude_desktop(
        env=env, name=None, create=False, force=False, yes=True, dry_run=True
    )
    typer.echo("")
    typer.echo("=== cursor ===")
    install_cursor(env=env, rules=False, project_dir=None, force=False, dry_run=True)
