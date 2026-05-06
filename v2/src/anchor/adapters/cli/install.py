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

install_app = typer.Typer(help="Register Anchor with an AI harness.")


# ── target descriptions ────────────────────────────────────────────────


def _claude_code_paths() -> tuple[Path, Path]:
    home = Path.home()
    return (home / ".claude" / "mcp.json", home / ".claude" / "skills" / "anchor")


def _cursor_paths() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


# ── skill template ─────────────────────────────────────────────────────

_SKILL_MD = """---
name: anchor
description: Use this skill when the user works with engineering PDFs (datasheets, leaflets, manuals, P&ID drawings) and wants to ingest them into a grounded knowledge base, query the structured contents, or build a workspace canvas where every value points back to its source page+bbox. Anchor exposes ingestion + workspace tools over MCP, so this skill is the right call any time the user says "ingest this PDF", "what does the leaflet say about X", "place that spec on the canvas", "wire this value into a simulation", or works with a folder of technical PDFs.
---

# Anchor — agent-first engineering knowledge canvas

Anchor turns a folder of engineering PDFs into a structured, source-grounded
knowledge base that you can drive over MCP. Every value you quote points
back to a specific page region.

## When to use

Trigger this skill when the user:
- Drops a PDF datasheet, leaflet, or manual and wants it readable
- Asks "what does this document say about X" or wants to look up specs
- Wants to place a spec table, document card, or region crop on a canvas
- Asks for help wiring a datasheet value into a simulation (FMU)
- Mentions a workspace folder or canvas
- Asks "where does this number come from?" — provenance is the whole point

## What's available

Two MCP tool sets, all under one server:

**Ingest tools** (act on the shared DOCS substrate):
- `ingest_pdf(pdf_path, slug?, skip_polish?, skip_regions?)` — bronze → silver → gold pipeline
- `list_documents()` — every document and its status
- `get_document_index(slug)` — silver outline (sections, tables, figures)
- `get_gold_regions(slug, page?)` — structured regions with page+bbox
- `get_page_text(slug, page)` — polished or raw page markdown

**Canvas tools** (act on a per-canvas WORKSPACES substrate):
- `canvas_create_workspace(slug, title?)` and `canvas_list_workspaces()`
- `canvas_get_state(workspace_slug)` — full canvas state
- `canvas_add_node(workspace_slug, node_type, label, x, y, data?)`
- `canvas_update_node(workspace_slug, id, ...)` and `canvas_remove_node(...)`
- `canvas_add_edge(workspace_slug, source, target, edge_type?, data?)`
- `canvas_remove_edge(workspace_slug, id)`
- `canvas_clear(workspace_slug)`

## Conventions

- **Always pass a workspace_slug.** Anchor is multi-canvas; create one
  per question/project (`canvas_create_workspace`) and reuse it.
- **Provenance is the contract.** When you place a spec value or quote
  a number, anchor it to the source via an edge with
  `data.kind = "evidence"` and `data.source_ref = {page, bbox}`.
  The system enforces this on `anchored` evidence edges.
- **Slug naming.** Document slugs are filename-derived (lowercase,
  hyphenated). Canvas slugs are user-chosen, e.g. `pump-analysis`.
- **Don't re-ingest.** `list_documents()` first; if the slug exists with
  `has_gold: true`, skip ingest unless the user asks for a fresh pass.

## Typical flow

1. `canvas_create_workspace(slug="pump-analysis")` — once
2. `ingest_pdf(pdf_path="/abs/path/to/datasheet.pdf")` if the user just dropped a PDF
3. `get_document_index(slug="alfa-laval-lkh")` — see what's in it
4. `get_gold_regions(slug="alfa-laval-lkh", page=2)` — get region IDs and bboxes
5. `canvas_add_node(workspace_slug="pump-analysis", node_type="document", label="LKH Pump", data={"slug": "alfa-laval-lkh", "page_count": 4})`
6. `canvas_add_node(...)` for spec rows, with `node_type="spec"` and `data.rows` carrying source refs
7. `canvas_add_edge(workspace_slug=..., source=..., target=..., edge_type="anchored", data={"kind": "evidence", "source_ref": {"page": 2, "bbox": [...]}}` to wire row → source

## Live state

The canvas has SSE; if a browser tab is open at the same time, the user
sees your changes appear live. Don't worry about cooperating with the
browser — the server is authoritative and serialises commands per
workspace.

## Where things live

Configured at install time. Default `~/anchor-data/`:
- `bronze/` raw PDFs
- `silver/<slug>/` per-page md + png
- `gold/<slug>/` structured regions with crops
- `canvases/<slug>/` per-canvas durable state + events log
"""


# ── installer impl ─────────────────────────────────────────────────────


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text().strip()
    if not text:
        return {}
    return json.loads(text)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


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


def _install_skill(skill_dir: Path, *, dry_run: bool) -> Path:
    skill_path = skill_dir / "SKILL.md"
    if not dry_run:
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(_SKILL_MD)
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
    skill_path = _install_skill(skill_dir, dry_run=dry_run)
    if not dry_run and not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(("[dry-run] " if dry_run else "") + f"MCP entry → {config_path}")
    typer.echo(f"          command: {entry['command']}")
    typer.echo(f"          args:    {entry['args']}")
    typer.echo(("[dry-run] " if dry_run else "") + f"Skill    → {skill_path}")
    typer.echo(("[dry-run] " if dry_run else "") + f"Data dir → {data_dir}")
    if not dry_run:
        typer.echo("")
        typer.echo("Next:")
        typer.echo("  1. Restart Claude Code (the MCP server list reloads on startup).")
        typer.echo("  2. /mcp in Claude Code should list 'anchor' with 17 tools.")
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

    typer.echo(("[dry-run] " if dry_run else "") + f"MCP entry → {config_path}")
    typer.echo(f"          command: {entry['command']}")
    typer.echo(f"          args:    {entry['args']}")
    typer.echo(("[dry-run] " if dry_run else "") + f"Data dir → {data_dir}")


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
