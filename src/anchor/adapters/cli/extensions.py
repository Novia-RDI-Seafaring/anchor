"""`anchor extensions ...` — manage OIP producer registrations.

Anchor is one OIP consumer; producers (PDF ingestion, transcription, code
indexing, …) drop manifests in known locations to be picked up. This
module handles the discovery + registration UX.

See `OIP.md` for the manifest schema and discovery rules.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.extension_host import (
    SOURCE_ORDER,
    discover_manifests,
    load_manifest,
    project_producers_dir,
    registration_dir,
    system_producers_dir,
)

extensions_app = typer.Typer(help="Inspect and manage canvas extensions (OIP producers).")


def _report_manifest_error(message: str) -> None:
    typer.echo(f"  [skip] {message}", err=True)


# ── Commands -------------------------------------------------------------


@extensions_app.command("list")
def extensions_list(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List every OIP producer this Anchor install can see.

    Discovery sources, in order:
      1. Bundled (compiled in)
      2. System  ~/.config/oip/producers.d/
      3. Project <data-dir>/.oip/producers.d/

    A producer registered in multiple sources is reported once per source
    so collisions are visible. Tools-namespace conflicts surface explicitly.
    """
    discovered = discover_manifests(
        data_dir if data_dir.exists() else None,
        on_error=_report_manifest_error,
    )
    if verbose:
        typer.echo(json.dumps(discovered, indent=2))
        return

    for source in SOURCE_ORDER:
        items = discovered.get(source, [])
        typer.echo(f"\n=== {source} ({len(items)}) ===")
        for m in items:
            p = m.get("producer", {})
            tools_ns = m.get("invocation", {}).get("tools_namespace", "?")
            kinds = m.get("produces", {}).get("source_kinds", [])
            typer.echo(f"  {p.get('name', '?'):<24} v{p.get('version', '?'):<8}  ns={tools_ns:<12} sources={kinds}")

    # Collision detection
    namespaces: dict[str, list[str]] = {}
    for source in SOURCE_ORDER:
        for m in discovered.get(source, []):
            ns = m.get("invocation", {}).get("tools_namespace")
            if ns:
                namespaces.setdefault(ns, []).append(f"{source}:{m['producer']['name']}")
    collisions = {ns: owners for ns, owners in namespaces.items() if len(owners) > 1}
    if collisions:
        typer.echo("\n[WARN] tools-namespace collisions:")
        for ns, owners in collisions.items():
            typer.echo(f"  '{ns}' claimed by: {', '.join(owners)}")


@extensions_app.command("info")
def extensions_info(
    name: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print the full manifest for one producer."""
    discovered = discover_manifests(
        data_dir if data_dir.exists() else None,
        on_error=_report_manifest_error,
    )
    for source in ("project", "system", "bundled"):    # project wins on collision
        for m in discovered.get(source, []):
            if m.get("producer", {}).get("name") == name:
                # Embed provenance into the JSON itself so consumers (including
                # tests) can parse the whole output.
                m_clean = {k: v for k, v in m.items() if not k.startswith("_")}
                m_clean["_anchor_source"] = source
                if "_manifest_path" in m:
                    m_clean["_anchor_path"] = m["_manifest_path"]
                typer.echo(json.dumps(m_clean, indent=2))
                return
    typer.echo(f"unknown producer: {name!r}", err=True)
    typer.echo("Run `anchor extensions list` to see what's available.", err=True)
    raise typer.Exit(code=1)


@extensions_app.command("add")
def extensions_add(
    manifest_path: Path,
    scope: str = typer.Option("system", "--scope", "-s", help="system | project"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """Register an OIP producer's manifest.

    `--scope system` writes to ~/.config/oip/producers.d/  (default; visible
    to every OIP consumer on the machine).

    `--scope project` writes to <data-dir>/.oip/producers.d/  (visible only
    when this data-dir is the active workspace root).
    """
    if not manifest_path.is_file():
        typer.echo(f"manifest not found: {manifest_path}", err=True)
        raise typer.Exit(code=1)

    m = load_manifest(manifest_path, on_error=_report_manifest_error)
    if m is None:
        typer.echo("manifest failed validation; aborting", err=True)
        raise typer.Exit(code=1)

    name = m["producer"]["name"]
    target_dir = registration_dir(scope, data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{name}.json"

    if target.exists() and not force:
        typer.echo(f"manifest already registered: {target}\nUse --force to overwrite.", err=True)
        raise typer.Exit(code=1)

    shutil.copy2(manifest_path, target)
    typer.echo(f"registered '{name}' -> {target}")


@extensions_app.command("remove")
def extensions_remove(
    name: str,
    scope: str = typer.Option("system", "--scope", "-s", help="system | project"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Unregister a producer (deletes its manifest file)."""
    target_dir = registration_dir(scope, data_dir)
    target = target_dir / f"{name}.json"
    if not target.exists():
        typer.echo(f"not registered in {scope}: {name!r}", err=True)
        raise typer.Exit(code=1)
    target.unlink()
    typer.echo(f"removed {name} from {target_dir}")


@extensions_app.command("discover")
def extensions_discover(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Show where Anchor looks for producer manifests.

    Use this to sanity-check that a third-party producer's installer wrote
    its manifest to the right place.
    """
    typer.echo("OIP producer discovery paths (in priority order):\n")
    typer.echo(f"  1. project   {project_producers_dir(data_dir)}")
    sys_dir = system_producers_dir()
    typer.echo(f"  2. system    {sys_dir}{'  (exists)' if sys_dir.exists() else '  (missing)'}")
    typer.echo("  3. bundled   compiled in")
    typer.echo("\nDrop a `*.json` manifest in either of the first two locations,")
    typer.echo("or run `anchor extensions add <path-to-manifest.json>` to register one.")
    typer.echo("\nSee OIP.md for the manifest schema.")


@extensions_app.command("schema")
def extensions_schema() -> None:
    """Print a minimal example OIP manifest. Save it as a starting point for your own producer."""
    example = {
        "oip_version": "0.1",
        "producer": {
            "name": "your-producer-name",
            "display_name": "Your Producer",
            "version": "0.1.0",
            "homepage": "https://github.com/your/repo",
        },
        "data_dir": "/abs/path/to/your/data/dir",
        "produces": {
            "source_kinds": ["audio/mp3", "audio/wav"],
            "region_kinds": ["transcript_segment"],
            "source_ref_kinds": ["audio-timestamp"],
        },
        "invocation": {
            "kind": "mcp-stdio",
            "command": "your-tool-mcp",
            "args": ["--data-dir", "/abs/path/to/your/data/dir"],
            "tools_namespace": "transcribe",
        },
        "ui_hints": {
            "node_types": [
                {"name": "transcribe:segment", "renders": "transcript with timestamp range"}
            ]
        },
    }
    typer.echo(json.dumps(example, indent=2))
