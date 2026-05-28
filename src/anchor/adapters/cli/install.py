"""`anchor install <target>` — register Anchor with an AI harness.

Targets:
    claude-code   Add MCP server entry to ~/.claude/mcp.json and write a
                  skill file at ~/.claude/skills/anchor/SKILL.md so Claude
                  Code knows when to use Anchor's tools.
    cursor        Add MCP server entry to ~/.cursor/mcp.json.
    print         Print what would be installed without writing anything.

Idempotent: existing entries are updated in place; re-running is safe.
The `--data-dir` becomes the default path the MCP server points at — you
can change it later by editing the config or by re-running `anchor install`.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import typer

from anchor.adapters.skills import compose_skill_md, discover_third_party_manifests

install_app = typer.Typer(help="Register Anchor with an AI harness.")


# ── target descriptions ────────────────────────────────────────────────


def _claude_code_paths() -> tuple[Path, Path]:
    home = Path.home()
    return (home / ".claude" / "mcp.json", home / ".claude" / "skills" / "anchor")


def _cursor_paths() -> Path:
    return Path.home() / ".cursor" / "mcp.json"



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
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _resolve_anchor_mcp() -> str:
    """Find the `anchor-mcp` binary or return the script path."""
    on_path = shutil.which("anchor-mcp")
    if on_path:
        return on_path
    # Fallback: the current Python's bin dir
    return str(Path(sys.executable).parent / "anchor-mcp")


def _build_mcp_entry(data_dir: Path) -> dict[str, Any]:
    return {
        "command": _resolve_anchor_mcp(),
        "args": ["--data-dir", str(data_dir.resolve())],
    }


def _install_mcp(config_path: Path, data_dir: Path, *, dry_run: bool) -> tuple[Path, dict[str, Any]]:
    cfg = _load_json(config_path)
    cfg.setdefault("mcpServers", {})
    cfg["mcpServers"]["anchor"] = _build_mcp_entry(data_dir)
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
    data_dir: Path = typer.Option(None, "--data-dir", "-d"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register Anchor as MCP server + skill in Claude Code."""
    if data_dir is None:
        data_dir = Path.home() / "anchor-data"
    mcp_config_path, skill_dir = _claude_code_paths()
    config_path, entry = _install_mcp(mcp_config_path, data_dir, dry_run=dry_run)
    skill_path = _install_skill(skill_dir, data_dir, dry_run=dry_run)
    if not dry_run and not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(("[dry-run] " if dry_run else "") + f"MCP entry -> {config_path}")
    typer.echo(f"          command: {entry['command']}")
    typer.echo(f"          args:    {entry['args']}")
    typer.echo(("[dry-run] " if dry_run else "") + f"Skill    -> {skill_path}")
    typer.echo(("[dry-run] " if dry_run else "") + f"Data dir -> {data_dir}")
    if not dry_run:
        typer.echo("")
        typer.echo("Next:")
        typer.echo("  1. Restart Claude Code (the MCP server list reloads on startup).")
        typer.echo("  2. /mcp in Claude Code should list 'anchor' with its available tools.")
        typer.echo("  3. Try: 'list anchor documents' or 'ingest this PDF: <path>'.")


@install_app.command("cursor")
def install_cursor(
    data_dir: Path = typer.Option(None, "--data-dir", "-d"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register Anchor as MCP server in Cursor."""
    if data_dir is None:
        data_dir = Path.home() / "anchor-data"
    config_path, entry = _install_mcp(_cursor_paths(), data_dir, dry_run=dry_run)
    if not dry_run and not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(("[dry-run] " if dry_run else "") + f"MCP entry -> {config_path}")
    typer.echo(f"          command: {entry['command']}")
    typer.echo(f"          args:    {entry['args']}")
    typer.echo(("[dry-run] " if dry_run else "") + f"Data dir -> {data_dir}")


@install_app.command("print")
def install_print(
    data_dir: Path = typer.Option(None, "--data-dir", "-d"),
) -> None:
    """Print the install plan for every supported target without writing."""
    if data_dir is None:
        data_dir = Path.home() / "anchor-data"
    typer.echo("=== claude-code ===")
    install_claude_code(data_dir=data_dir, dry_run=True)
    typer.echo("")
    typer.echo("=== cursor ===")
    install_cursor(data_dir=data_dir, dry_run=True)
