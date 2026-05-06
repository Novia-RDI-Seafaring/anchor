"""`anchor extensions ...` — manage OIP producer registrations.

Anchor is one OIP consumer; producers (PDF ingestion, transcription, code
indexing, …) drop manifests in known locations to be picked up. This
module handles the discovery + registration UX.

See `OIP.md` for the manifest schema and discovery rules.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import typer

extensions_app = typer.Typer(help="Inspect and manage canvas extensions (OIP producers).")


# ── Locations -------------------------------------------------------------


def _system_producers_dir() -> Path:
    """The shared, system-wide producer-registration directory.

    Follows XDG conventions: $XDG_CONFIG_HOME/oip/producers.d/, falling back
    to ~/.config/oip/producers.d/. Any installer can drop a manifest here
    and every OIP-aware consumer on the machine picks it up.
    """
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "oip" / "producers.d"


def _project_producers_dir(data_dir: Path) -> Path:
    """Per-canvas-data-dir registrations (highest priority)."""
    return data_dir / ".oip" / "producers.d"


def _bundled_producers() -> list[dict[str, Any]]:
    """Producers that ship in-tree with this Anchor build."""
    from anchor import __version__
    from anchor.extensions.anchor_cad import extension as cad_ext
    from anchor.extensions.anchor_fmus import extension as fmu_ext
    return [
        {
            "oip_version": "0.1",
            "producer": {
                "name": "anchor-pdfs",
                "display_name": "Anchor PDFs",
                "version": __version__,
                "homepage": "https://github.com/Novia-RDI-Seafaring/anchor-kb-ui-RAG",
            },
            "kind": "bundled-in-tree",
            "produces": {
                "source_kinds": ["application/pdf"],
                "region_kinds": ["table", "spec_block", "chart", "diagram", "figure", "text"],
                "source_ref_kinds": ["pdf-page-bbox"],
            },
            "invocation": {
                "kind": "mcp-stdio",
                "command": "anchor-mcp",
                "args": [],
                "tools_namespace": "pdf",
            },
            "ui_hints": {
                "node_types": [
                    {"name": "pdf:document", "renders": "document"},
                    {"name": "pdf:spec_table", "renders": "spec_block regions"},
                    {"name": "pdf:image", "renders": "figure/diagram regions"},
                ],
                "edge_styles": {
                    "pdf:evidence": {"stroke": "#FF8E2B", "dasharray": "4 4"}
                },
                "source_ref_handlers": {
                    "pdf-page-bbox": "open the PDF at the given page, draw the bbox"
                },
            },
        },
        fmu_ext.manifest(),
        cad_ext.manifest(),
    ]


def _load_manifest(path: Path) -> dict[str, Any] | None:
    """Read + minimally validate a manifest. Returns None on failure (with stderr echo)."""
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        typer.echo(f"  [skip] {path}: {e}", err=True)
        return None
    if "oip_version" not in data or "producer" not in data:
        typer.echo(f"  [skip] {path}: not an OIP manifest (missing oip_version/producer)", err=True)
        return None
    data["_manifest_path"] = str(path)
    return data


def _discover(data_dir: Path | None) -> dict[str, list[dict[str, Any]]]:
    """Walk every known location, return manifests grouped by source.

    Resolution order (highest priority last in a name-collision merge):
        bundled in-tree  →  system  →  project (per data-dir)
    """
    found: dict[str, list[dict[str, Any]]] = {
        "bundled": _bundled_producers(),
        "system": [],
        "project": [],
    }

    sys_dir = _system_producers_dir()
    if sys_dir.is_dir():
        for p in sorted(sys_dir.glob("*.json")):
            m = _load_manifest(p)
            if m is not None:
                found["system"].append(m)

    if data_dir is not None:
        proj_dir = _project_producers_dir(data_dir)
        if proj_dir.is_dir():
            for p in sorted(proj_dir.glob("*.json")):
                m = _load_manifest(p)
                if m is not None:
                    found["project"].append(m)

    return found


# ── Commands -------------------------------------------------------------


@extensions_app.command("list")
def extensions_list(
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
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
    discovered = _discover(data_dir if data_dir.exists() else None)
    if verbose:
        typer.echo(json.dumps(discovered, indent=2))
        return

    for source in ("bundled", "system", "project"):
        items = discovered.get(source, [])
        typer.echo(f"\n=== {source} ({len(items)}) ===")
        for m in items:
            p = m.get("producer", {})
            tools_ns = m.get("invocation", {}).get("tools_namespace", "?")
            kinds = m.get("produces", {}).get("source_kinds", [])
            typer.echo(f"  {p.get('name', '?'):<24} v{p.get('version', '?'):<8}  ns={tools_ns:<12} sources={kinds}")

    # Collision detection
    namespaces: dict[str, list[str]] = {}
    for source in ("bundled", "system", "project"):
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
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Print the full manifest for one producer."""
    discovered = _discover(data_dir if data_dir.exists() else None)
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
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
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

    m = _load_manifest(manifest_path)
    if m is None:
        typer.echo("manifest failed validation; aborting", err=True)
        raise typer.Exit(code=1)

    name = m["producer"]["name"]
    target_dir = _project_producers_dir(data_dir) if scope == "project" else _system_producers_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{name}.json"

    if target.exists() and not force:
        typer.echo(f"manifest already registered: {target}\nUse --force to overwrite.", err=True)
        raise typer.Exit(code=1)

    shutil.copy2(manifest_path, target)
    typer.echo(f"registered '{name}' → {target}")


@extensions_app.command("remove")
def extensions_remove(
    name: str,
    scope: str = typer.Option("system", "--scope", "-s", help="system | project"),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Unregister a producer (deletes its manifest file)."""
    target_dir = _project_producers_dir(data_dir) if scope == "project" else _system_producers_dir()
    target = target_dir / f"{name}.json"
    if not target.exists():
        typer.echo(f"not registered in {scope}: {name!r}", err=True)
        raise typer.Exit(code=1)
    target.unlink()
    typer.echo(f"removed {name} from {target_dir}")


@extensions_app.command("discover")
def extensions_discover(
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Show where Anchor looks for producer manifests.

    Use this to sanity-check that a third-party producer's installer wrote
    its manifest to the right place.
    """
    typer.echo("OIP producer discovery paths (in priority order):\n")
    typer.echo(f"  1. project   {_project_producers_dir(data_dir)}")
    sys_dir = _system_producers_dir()
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
