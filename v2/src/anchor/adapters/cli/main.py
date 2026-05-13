"""`anchor` CLI entrypoint (Typer)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from anchor.adapters.cli.extensions import extensions_app
from anchor.adapters.cli.install import install_app

app = typer.Typer(help="Anchor — agent-first knowledge canvas.")
canvas_app = typer.Typer(help="Manage workspaces (canvases).")
sysml_app = typer.Typer(help="Render and export SysML v2 diagrams.")
app.add_typer(canvas_app, name="canvas")
app.add_typer(sysml_app, name="sysml")
app.add_typer(install_app, name="install")
app.add_typer(extensions_app, name="extensions")


def _build_real_services(data_dir: Path, *, base_url: str = "http://localhost:8002"):
    """Wire concrete adapters. Polish/region-extract are OpenAI-only and become
    no-ops if the user hasn't provided ANCHOR_OPENAI_API_KEY — silver still
    builds, gold simply skips. Embeddings default to a local sentence-
    transformer model; OpenAI is opt-in via ANCHOR_OPENAI_API_KEY.

    `base_url` is where the wired SnapshotPort points headless chromium.
    Default matches `anchor serve --port 8002`; override when serving on a
    non-default port."""
    from anchor.extensions.anchor_pdfs.core.services import IngestService
    from anchor.core.services.workspace_service import WorkspaceService
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from anchor.infra.config import AnchorConfig
    from anchor.extensions.anchor_pdfs.infra.llm.openai_md_polisher import OpenAIPageMdPolisher
    from anchor.extensions.anchor_pdfs.infra.llm.openai_region_extractor import OpenAIRegionExtractor
    from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
    from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.infra.snapshot.headless_chromium_snapshotter import (
        HeadlessChromiumSnapshotter,
    )
    from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore

    import os

    config = AnchorConfig(data_dir=data_dir)
    bus = MemoryEventBus()
    workspace_store = FsWorkspaceStore(config.canvases_dir)
    doc_store = FsDocStore(config.data_dir)
    snapshotter = HeadlessChromiumSnapshotter(
        base_url=base_url,
        output_dir=config.data_dir / "snapshots",
    )
    workspace = WorkspaceService(workspace_store, bus, snapshotter=snapshotter)
    api_key = config.openai_api_key.get_secret_value() if config.openai_api_key else None
    # OpenAI SDK reads OPENAI_API_KEY from env by default; instantiate if either path
    # has a key so polish/region steps don't silently no-op.
    has_openai = bool(api_key) or bool(os.environ.get("OPENAI_API_KEY"))
    ingest = IngestService(
        doc_store, bus,
        extractor=DoclingPdfExtractor(),
        renderer=PymupdfPdfRenderer(),
        polisher=OpenAIPageMdPolisher(api_key=api_key) if has_openai else None,
        region_extractor=OpenAIRegionExtractor(api_key=api_key) if has_openai else None,
    )
    return config, bus, workspace, ingest, doc_store


def _build_embedder(api_key: str | None):
    """Local-first: sentence-transformers if installed, OpenAI as fallback.

    Returning None is fine — the embedder is only used when query/embed
    commands run; absence is a soft failure, not a hard one."""
    if api_key:
        try:
            from anchor.extensions.anchor_pdfs.infra.llm.openai_embedder import OpenAIEmbedder
            return OpenAIEmbedder(api_key=api_key)
        except ImportError:
            pass
    try:
        from anchor.extensions.anchor_pdfs.infra.llm.local_sentence_transformer_embedder import (
            LocalSentenceTransformerEmbedder,
        )
        return LocalSentenceTransformerEmbedder()
    except ImportError:
        return None


@app.command()
def serve(
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8002, "--port", "-p"),
) -> None:
    """Run the HTTP adapter (FastAPI + SSE) and serve the frontend bundle."""
    import uvicorn

    from anchor.adapters.http.app import build_app

    # The snapshotter points at the same server we're about to start so
    # snapshots taken via CLI / MCP loop back to this process.
    base_url = f"http://localhost:{port}"
    _, bus, workspace, ingest, doc_store = _build_real_services(data_dir, base_url=base_url)
    static_dir = Path(__file__).resolve().parents[2] / "_web_dist"
    if not static_dir.is_dir():
        # development: walk up to v2/web/dist
        static_dir = Path(__file__).resolve().parents[4] / "web" / "dist"

    # Wire the CAD extension service. Manifest already lives in
    # _bundled_producers; the service handles ingestion and storage.
    from anchor.extensions.anchor_cad import extension as cad_ext
    cad_service = cad_ext.build_service(data_dir, bus)

    # Wire the SysML extension — pure-Python, always available.
    from anchor.extensions.anchor_sysml import extension as sysml_ext
    sysml_service = sysml_ext.build_service(data_dir, bus, workspace=workspace)

    # Wire the synopsis service — pdf + marp renderers are first-party.
    from anchor.extensions.anchor_pdfs.core.services import SynopsisService
    from anchor.extensions.anchor_pdfs.infra.synopsis_renderers import (
        MarpSynopsisRenderer, PymupdfSynopsisRenderer,
    )
    synopsis_service = SynopsisService(
        doc_store,
        pdf_renderer=PymupdfSynopsisRenderer(),
        md_renderer=MarpSynopsisRenderer(),
    )

    app_ = build_app(
        workspace_service=workspace,
        ingest_service=ingest,
        doc_store=doc_store,
        bus=bus,
        static_dir=static_dir if static_dir.is_dir() else None,
        cad_service=cad_service,
        sysml_service=sysml_service,
        synopsis_service=synopsis_service,
    )
    typer.echo(f"[anchor serve] data_dir={data_dir} {host}:{port}")
    uvicorn.run(app_, host=host, port=port)


@app.command()
def ingest(
    pdf_path: Path = typer.Argument(...),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
    skip_polish: bool = typer.Option(False, "--skip-polish"),
    skip_regions: bool = typer.Option(False, "--skip-regions"),
) -> None:
    """Run a PDF through the bronze → silver → gold pipeline."""
    if not pdf_path.exists():
        typer.echo(f"PDF not found: {pdf_path}", err=True)
        raise typer.Exit(code=1)
    config, _, _, ingest_svc, _ = _build_real_services(data_dir)

    async def run() -> dict:
        return await ingest_svc.ingest_pdf(
            pdf_path.read_bytes(), pdf_path.name,
            polish=not skip_polish, regions=not skip_regions,
            polish_model=config.polish_model,
            region_model=config.region_model,
            dpi=config.dpi,
        )

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@app.command("list")
def list_documents(
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """List all ingested documents."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(doc_store.list_documents()), indent=2))


@app.command()
def index(
    slug: str,
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Print the silver index for a document."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    out = asyncio.run(doc_store.get_index(slug))
    if out is None:
        typer.echo(f"no index for {slug!r}", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(out, indent=2))


@app.command()
def regions(
    slug: str,
    page: int | None = typer.Option(None, "--page", "-p"),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Print gold regions for a document, optionally filtered to a page."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(doc_store.get_regions(slug, page=page)), indent=2))


@app.command("page-text")
def page_text(
    slug: str,
    page: int,
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Print polished or raw markdown for a page."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    text = asyncio.run(doc_store.get_page_text(slug, page))
    if text is None:
        typer.echo(f"no text for {slug}:{page}", err=True)
        raise typer.Exit(code=1)
    typer.echo(text)


# ── Read-byte commands (parity with MCP get_page_image / get_crop / get_pdf) ─
#
# Default `path` prints the on-disk path — agents on the same machine read
# it directly. `--copy-to <dest>` resolves the path and copies bytes.
# `--out -` writes the raw bytes to stdout (for piping into imagemagick,
# pdftotext, etc.).

@app.command("gold-map")
def gold_map(
    slug: str,
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Print the full gold extraction JSON (document + outline + regions + page meta)."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    out = asyncio.run(doc_store.get_gold_map(slug))
    if out is None:
        typer.echo(f"no gold map for {slug!r}", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps(out, indent=2))


def _emit_bytes(path: Path | None, *, copy_to: Path | None, out: str | None, label: str) -> None:
    if path is None:
        typer.echo(f"{label}: not found", err=True)
        raise typer.Exit(code=1)
    if str(path).startswith("memory://"):
        typer.echo(f"{label}: in-memory store has no real path", err=True)
        raise typer.Exit(code=1)
    if out == "-":
        # Binary safe — write raw bytes through the underlying stdout buffer.
        import sys
        sys.stdout.buffer.write(path.read_bytes())
        return
    if copy_to is not None:
        copy_to.parent.mkdir(parents=True, exist_ok=True)
        copy_to.write_bytes(path.read_bytes())
        typer.echo(str(copy_to))
        return
    typer.echo(str(path))


@app.command("page-image")
def page_image(
    slug: str,
    page: int,
    copy_to: Path | None = typer.Option(None, "--copy-to"),
    out: str | None = typer.Option(None, "--out", help="Pass '-' to stream the bytes to stdout."),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Page screenshot. Prints the path by default; --copy-to or --out - for the bytes."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    path = asyncio.run(doc_store.get_page_image_path(slug, page))
    _emit_bytes(path, copy_to=copy_to, out=out, label=f"{slug} page {page}")


@app.command("crop")
def crop(
    slug: str,
    rel_path: str,
    copy_to: Path | None = typer.Option(None, "--copy-to"),
    out: str | None = typer.Option(None, "--out"),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Gold-extracted region crop (e.g. '4/r1.png') by its rel_path."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    path = asyncio.run(doc_store.get_crop_path(slug, rel_path))
    _emit_bytes(path, copy_to=copy_to, out=out, label=f"{slug} crop {rel_path}")


@app.command("pdf")
def pdf(
    slug: str,
    copy_to: Path | None = typer.Option(None, "--copy-to"),
    out: str | None = typer.Option(None, "--out"),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """The original bronze-layer PDF for a document."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    path = asyncio.run(doc_store.get_raw_pdf_path(slug))
    _emit_bytes(path, copy_to=copy_to, out=out, label=f"{slug} pdf")


@app.command("synopsis")
def synopsis(
    slug: str,
    entity: str = typer.Option(..., "--entity", "-e", help="e.g. 'LKH-5'"),
    format: str = typer.Option("json", "--format", "-f", help="json | pdf | md"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write artefact to this path (for pdf/md)."),
    crop_url_base: str | None = typer.Option(None, "--crop-url-base", help="(md only) URL prefix for crop references."),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Compose an entity-scoped synopsis from gold data.

    `--format json` (default): prints SynopsisData as JSON to stdout.
    `--format pdf`: writes a multi-page PDF synopsis (cover + specs + charts).
    `--format md`: writes a Marp-compatible markdown slide deck.
    """
    _, _, _, _, doc_store = _build_real_services(data_dir)
    from anchor.extensions.anchor_pdfs.core.services import SynopsisService
    from anchor.extensions.anchor_pdfs.infra.synopsis_renderers import (
        MarpSynopsisRenderer, PymupdfSynopsisRenderer,
    )
    svc = SynopsisService(
        doc_store,
        pdf_renderer=PymupdfSynopsisRenderer(),
        md_renderer=MarpSynopsisRenderer(),
    )

    if format == "json":
        from dataclasses import asdict
        async def run():
            return asdict(await svc.compose(slug=slug, entity=entity))
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
        return
    if format == "pdf":
        async def run():
            return await svc.render_pdf(slug=slug, entity=entity)
        pdf_bytes = asyncio.run(run())
        if output is None:
            output = Path(f"{slug}-{entity}.pdf")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(pdf_bytes)
        typer.echo(str(output))
        return
    if format == "md":
        async def run():
            return await svc.render_markdown(slug=slug, entity=entity, crop_url_base=crop_url_base)
        md = asyncio.run(run())
        if output is None:
            typer.echo(md)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(md)
            typer.echo(str(output))
        return
    typer.echo(f"unknown --format {format!r} (use json | pdf | md)", err=True)
    raise typer.Exit(code=2)


@canvas_app.command("list")
def canvas_list(
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """List all workspaces."""
    _, _, ws, _, _ = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(ws.list_workspaces()), indent=2))


@canvas_app.command("create")
def canvas_create(
    slug: str,
    title: str = typer.Option("", "--title"),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Create a new workspace folder."""
    _, _, ws, _, _ = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(ws.create_workspace(slug, title=title)), indent=2))


# ── Canvas mutations ────────────────────────────────────────────────────────
#
# Every command below is a thin wrapper around the same `WorkspaceService`
# method that the HTTP router and MCP handler call. The work happens in
# CORE; this file only translates flags into kwargs. Keeping all three
# adapters in lockstep is the architecture's standing rule
# (see `v2/docs/06-many-interfaces.md`).
#
# `--data` accepts a JSON string. Shells are awkward at JSON quoting; for
# multi-field nodes use a here-doc or pipe through a file:
#   anchor canvas add-node my-canvas concept Foo --x 0 --y 0 \
#     --data "$(cat <<'JSON'
#   {"subtitle": "hello", "metadata": {"tag": "demo"}}
#   JSON
#   )"


def _parse_data(raw: str | None) -> dict:
    if raw is None or raw == "":
        return {}
    try:
        out = json.loads(raw)
    except json.JSONDecodeError as e:
        typer.echo(f"--data is not valid JSON: {e}", err=True)
        raise typer.Exit(code=2)
    if not isinstance(out, dict):
        typer.echo("--data must be a JSON object", err=True)
        raise typer.Exit(code=2)
    return out


@canvas_app.command("state")
def canvas_state(
    slug: str,
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Print the full workspace state (nodes + edges + metadata)."""
    _, _, ws, _, _ = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(ws.get_state(slug)), indent=2))


@canvas_app.command("add-node")
def canvas_add_node(
    slug: str,
    node_type: str,
    label: str = typer.Option("", "--label", "-l"),
    x: float = typer.Option(0.0, "--x"),
    y: float = typer.Option(0.0, "--y"),
    width: float | None = typer.Option(None, "--width"),
    height: float | None = typer.Option(None, "--height"),
    parent: str | None = typer.Option(None, "--parent"),
    data: str | None = typer.Option(None, "--data", help="JSON object passed as the node's `data` field"),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Add a node to a workspace. Prints the resulting `{event, state}`."""
    _, _, ws, _, _ = _build_real_services(data_dir)
    kwargs: dict = {"node_type": node_type, "label": label, "x": x, "y": y, "data": _parse_data(data)}
    if width is not None: kwargs["width"] = width
    if height is not None: kwargs["height"] = height
    if parent is not None: kwargs["parent"] = parent

    async def run():
        state, env = await ws.add_node(slug, **kwargs)
        return {"event": env.model_dump(), "state": state.get_state()}
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("update-node")
def canvas_update_node(
    slug: str,
    node_id: str,
    label: str | None = typer.Option(None, "--label", "-l"),
    x: float | None = typer.Option(None, "--x"),
    y: float | None = typer.Option(None, "--y"),
    width: float | None = typer.Option(None, "--width"),
    height: float | None = typer.Option(None, "--height"),
    data: str | None = typer.Option(None, "--data"),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Update fields on an existing node. Move-only when only --x and --y given."""
    _, _, ws, _, _ = _build_real_services(data_dir)
    fields: dict = {}
    if label is not None:  fields["label"] = label
    if x is not None:      fields["x"] = x
    if y is not None:      fields["y"] = y
    if width is not None:  fields["width"] = width
    if height is not None: fields["height"] = height
    if data is not None:   fields["data"] = _parse_data(data)
    if not fields:
        typer.echo("nothing to update — pass at least one field", err=True)
        raise typer.Exit(code=2)

    async def run():
        # Same heuristic as the HTTP PATCH route: a pure move is dispatched
        # through `move_node` for the event-type clarity.
        if set(fields.keys()) == {"x", "y"}:
            state, env = await ws.move_node(slug, node_id, fields["x"], fields["y"])
        else:
            state, env = await ws.update_node(slug, node_id, fields)
        return {"event": env.model_dump(), "state": state.get_state()}
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("remove-node")
def canvas_remove_node(
    slug: str,
    node_id: str,
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Remove a node and any edges that touched it (cascade is in CORE)."""
    _, _, ws, _, _ = _build_real_services(data_dir)

    async def run():
        state, envelopes = await ws.remove_node(slug, node_id)
        return {"events": [e.model_dump() for e in envelopes], "state": state.get_state()}
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("add-edge")
def canvas_add_edge(
    slug: str,
    source: str,
    target: str,
    edge_type: str = typer.Option("floating", "--type", "-t", help="`floating` or `anchored`"),
    label: str = typer.Option("", "--label", "-l"),
    source_handle: str | None = typer.Option(None, "--source-handle"),
    target_handle: str | None = typer.Option(None, "--target-handle"),
    data: str | None = typer.Option(None, "--data"),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Add an edge between two nodes."""
    _, _, ws, _, _ = _build_real_services(data_dir)
    payload = _parse_data(data)
    kwargs: dict = {"source": source, "target": target, "edge_type": edge_type, "label": label, "data": payload}
    if source_handle: kwargs["source_handle"] = source_handle
    if target_handle: kwargs["target_handle"] = target_handle

    async def run():
        state, env = await ws.add_edge(slug, **kwargs)
        return {"event": env.model_dump(), "state": state.get_state()}
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("remove-edge")
def canvas_remove_edge(
    slug: str,
    edge_id: str,
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Remove a single edge by id."""
    _, _, ws, _, _ = _build_real_services(data_dir)

    async def run():
        state, env = await ws.remove_edge(slug, edge_id)
        return {"event": env.model_dump(), "state": state.get_state()}
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("clear")
def canvas_clear(
    slug: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm — clear removes EVERY node and edge on the workspace."),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Remove every node and edge from a workspace (workspace itself stays)."""
    if not yes:
        typer.echo("Refusing to clear without --yes; pass -y to confirm.", err=True)
        raise typer.Exit(code=2)
    _, _, ws, _, _ = _build_real_services(data_dir)

    async def run():
        state, env = await ws.clear(slug)
        return {"event": env.model_dump(), "state": state.get_state()}
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@sysml_app.command("render")
def sysml_render(
    sysml_path: Path = typer.Argument(...),
    workspace_slug: str = typer.Option(..., "--workspace", "-w"),
    x_offset: float = typer.Option(0.0, "--x-offset"),
    y_offset: float = typer.Option(0.0, "--y-offset"),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Render a .sysml file's contents onto the named workspace."""
    if not sysml_path.exists():
        typer.echo(f"SysML file not found: {sysml_path}", err=True)
        raise typer.Exit(code=1)
    _, bus, workspace, _, _ = _build_real_services(data_dir)
    from anchor.extensions.anchor_sysml import extension as sysml_ext
    svc = sysml_ext.build_service(data_dir, bus, workspace=workspace)

    async def run():
        return await svc.render(
            workspace_slug=workspace_slug,
            text=sysml_path.read_text(),
            x_offset=x_offset,
            y_offset=y_offset,
            filename=sysml_path.name,
        )

    typer.echo(json.dumps(asyncio.run(run()).model_dump(), indent=2))


@sysml_app.command("export")
def sysml_export(
    workspace_slug: str = typer.Argument(...),
    data_dir: Path = typer.Option(Path("./data"), "--data-dir", "-d"),
) -> None:
    """Export the workspace's SysML elements back to text (Phase 1 stub)."""
    _, bus, workspace, _, _ = _build_real_services(data_dir)
    from anchor.extensions.anchor_sysml import extension as sysml_ext
    svc = sysml_ext.build_service(data_dir, bus, workspace=workspace)

    async def run():
        return await svc.export(workspace_slug=workspace_slug)

    typer.echo(asyncio.run(run()))


@app.command()
def version() -> None:
    """Print the installed Anchor version."""
    from anchor import __version__
    typer.echo(__version__)


if __name__ == "__main__":
    app()
