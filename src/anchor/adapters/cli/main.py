"""`anchor` CLI entrypoint (Typer)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

from anchor.adapters.cli.extensions import extensions_app
from anchor.adapters.cli.install import install_app

# Canonical data dir. Per project memory the standard location is
# `~/anchor-data` so a fresh `anchor serve` / `anchor ingest` from any
# cwd lands at the same place. Override with `--data-dir` or env
# `ANCHOR_DATA_DIR`.
DEFAULT_DATA_DIR = Path.home() / "anchor-data"

app = typer.Typer(help="Anchor - agent-first knowledge canvas.")
canvas_app = typer.Typer(help="Manage workspaces (canvases).")
sysml_app = typer.Typer(help="Render and export SysML v2 diagrams.")
fmu_app = typer.Typer(help="Inspect and simulate FMU models.")
cad_app = typer.Typer(help="Inspect and parameter-tweak CAD models.")
app.add_typer(canvas_app, name="canvas")
app.add_typer(sysml_app, name="sysml")
app.add_typer(fmu_app, name="fmu")
app.add_typer(cad_app, name="cad")
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
    # base_url lets users point polish/region at an OpenAI-compatible
    # backend (Azure OpenAI, Ollama, vLLM, LM Studio). Empty string is
    # treated the same as None so a stray env var doesn't break stock
    # OpenAI usage.
    openai_base_url = (config.openai_base_url or "").strip() or None
    embedder = _build_embedder(
        api_key if has_openai else None,
        base_url=openai_base_url,
        local_model=config.embed_model,
    )
    ingest = IngestService(
        doc_store, bus,
        extractor=DoclingPdfExtractor(),
        renderer=PymupdfPdfRenderer(),
        polisher=OpenAIPageMdPolisher(api_key=api_key, base_url=openai_base_url) if has_openai else None,
        region_extractor=OpenAIRegionExtractor(api_key=api_key, base_url=openai_base_url) if has_openai else None,
        embedder=embedder,
        embed_model_id=getattr(embedder, "model_id", None),
        default_polish_model=config.polish_model,
        default_region_model=config.region_model,
        default_dpi=config.dpi,
    )
    return config, bus, workspace, ingest, doc_store


def _build_embedder(
    api_key: str | None,
    *,
    base_url: str | None = None,
    local_model: str = "BAAI/bge-small-en-v1.5",
):
    """Local-first: sentence-transformers if installed, OpenAI as fallback.

    Returning None is fine — the embedder is only used when query/embed
    commands run; absence is a soft failure, not a hard one."""
    if api_key:
        try:
            from anchor.extensions.anchor_pdfs.infra.llm.openai_embedder import OpenAIEmbedder
            return OpenAIEmbedder(api_key=api_key, base_url=base_url)
        except ImportError:
            pass
    try:
        from anchor.extensions.anchor_pdfs.infra.llm.local_sentence_transformer_embedder import (
            LocalSentenceTransformerEmbedder,
        )
        return LocalSentenceTransformerEmbedder(model=local_model)
    except ImportError:
        return None


@app.command()
def serve(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help=(
            "Bind address. Defaults to 127.0.0.1 (loopback) because the HTTP "
            "server is unauthenticated. Pass --host 0.0.0.0 to expose to "
            "your LAN - you are responsible for fronting it with auth."
        ),
    ),
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

    # Wire the FMU extension — optional. Real runtime requires FMPy
    # (`uv tool install 'anchor-kb[fmus]'`); the synthetic demo runtime is
    # gated behind ANCHOR_FMU_DEMO=1. Without either, build_service now
    # raises FmuRuntimeUnavailableError (we deliberately do NOT silently
    # mount the fake runtime — see the OSS review). The user sees a
    # one-line hint and the server boots fine without the FMU routes.
    fmu_service = None
    try:
        from anchor.extensions.anchor_fmus import extension as fmu_ext
        fmu_service = fmu_ext.build_service(data_dir, bus)
    except fmu_ext.FmuRuntimeUnavailableError as exc:
        typer.echo(f"Warning: FMU extension disabled: {exc}", err=True)
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"Warning: FMU extension failed to start: {exc}", err=True)

    app_ = build_app(
        workspace_service=workspace,
        ingest_service=ingest,
        doc_store=doc_store,
        bus=bus,
        static_dir=static_dir if static_dir.is_dir() else None,
        cad_service=cad_service,
        sysml_service=sysml_service,
        synopsis_service=synopsis_service,
        fmu_service=fmu_service,
        canvases_dir=data_dir / "canvases",
    )
    typer.echo(f"[anchor serve] data_dir={data_dir} {host}:{port}")
    uvicorn.run(app_, host=host, port=port)


@app.command()
def ingest(
    pdf_path: Path = typer.Argument(...),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    skip_polish: bool = typer.Option(False, "--skip-polish"),
    skip_regions: bool = typer.Option(False, "--skip-regions"),
) -> None:
    """Run a PDF through the bronze -> silver -> gold pipeline."""
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List all ingested documents."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(doc_store.list_documents()), indent=2))


@app.command()
def search(
    query: str = typer.Argument(..., help="Free-text query."),
    k: int = typer.Option(10, "--k", "-k", help="Top-k hits to return."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Semantic search across every gold-extracted, embedded document.

    Returns top-k grounded hits with (slug, page, region_id, text, score).
    Requires that documents have been embedded first via `anchor embed`.
    """
    _, _, _, ingest_svc, _ = _build_real_services(data_dir)
    if ingest_svc.embedder is None:
        typer.echo("no embedder wired - install sentence-transformers (uv add sentence-transformers)", err=True)
        raise typer.Exit(code=1)
    out = asyncio.run(ingest_svc.search(query, k=k))
    typer.echo(json.dumps(out, indent=2))


@app.command()
def embed(
    slug: str | None = typer.Argument(None, help="Single doc slug; omit to embed all gold-extracted docs that don't have embeddings yet."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Re-embed even if embeddings.json already exists."),
) -> None:
    """Embed gold regions of a document and persist to embeddings.json.

    Uses the local sentence-transformer embedder (BAAI/bge-small-en-v1.5
    by default). Auto-runs at the end of `anchor ingest`; this command
    backfills already-ingested docs without re-running the full pipeline.
    """
    _, _, _, ingest_svc, doc_store = _build_real_services(data_dir)
    if ingest_svc.embedder is None:
        typer.echo("no embedder wired - install sentence-transformers (uv add sentence-transformers)", err=True)
        raise typer.Exit(code=1)

    async def run_all() -> list[dict]:
        slugs: list[str]
        if slug is not None:
            slugs = [slug]
        else:
            docs = await doc_store.list_documents()
            slugs = [d["slug"] for d in docs if d.get("has_gold")]
        out: list[dict] = []
        for s in slugs:
            existing = await doc_store.get_embeddings(s)
            if existing and not overwrite:
                out.append({"slug": s, "skipped": True, "reason": "already embedded", "embed_model": existing.get("embed_model")})
                continue
            n = await ingest_svc.embed_document(s)
            out.append({"slug": s, "embedded": n, "embed_model": ingest_svc.embed_model_id})
        return out

    typer.echo(json.dumps(asyncio.run(run_all()), indent=2))


@app.command()
def index(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print gold regions for a document, optionally filtered to a page."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(doc_store.get_regions(slug, page=page)), indent=2))


@app.command("embeddings-meta")
def embeddings_meta(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print embeddings.json metadata (model id, dim, vector count, ts).

    Useful for verifying which embed_model a doc was indexed with
    before issuing a semantic query — clients need to load the matching
    bundle on their side.
    """
    _, _, _, _, doc_store = _build_real_services(data_dir)
    data = asyncio.run(doc_store.get_embeddings(slug))
    if data is None:
        typer.echo(f"no embeddings for {slug!r}", err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps({
        "slug": slug,
        "embed_model": data.get("embed_model"),
        "dim": data.get("dim"),
        "embedded_at": data.get("embedded_at"),
        "vector_count": len(data.get("vectors", [])),
    }, indent=2))


@app.command("page-text")
def page_text(
    slug: str,
    page: int,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    format: str = typer.Option(
        "text", "--format", "-f",
        help="'text' for one-per-line summary, 'json' for the full envelope.",
    ),
) -> None:
    """List all workspaces with counts + reference edges.

    ``--format text`` (default) prints one canvas per line as
    ``slug - N nodes / M edges / refs N / refd-by M``. ``--format json``
    prints the full envelope including the ``references`` /
    ``referenced_by`` slug lists — same shape returned by the HTTP
    ``GET /api/workspaces`` and the ``canvas_list_workspaces`` MCP tool.
    """
    _, _, ws, _, _ = _build_real_services(data_dir)
    items = asyncio.run(ws.list_workspaces())
    if format == "json":
        typer.echo(json.dumps(items, indent=2))
        return
    if format != "text":
        typer.echo(f"unknown --format {format!r} (use 'text' or 'json')", err=True)
        raise typer.Exit(code=2)
    if not items:
        typer.echo("(no canvases)")
        return
    for it in items:
        typer.echo(
            f"{it['slug']} - {it['node_count']} nodes / "
            f"{it['edge_count']} edges / refs {len(it['references'])} / "
            f"refd-by {len(it['referenced_by'])}",
        )


@canvas_app.command("placeholders")
def canvas_placeholders(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    format: str = typer.Option(
        "text", "--format", "-f",
        help="'text' (one per line) or 'json' (the full list).",
    ),
) -> None:
    """List the workspace's placeholder nodes (``data.placeholder == true``).

    Mirrors the ``canvas_list_placeholders`` MCP tool + the HTTP
    ``GET /api/workspaces/{slug}/placeholders`` route. Each entry carries
    ``{id, node_type, label, hint, x, y, data}``; the ``hint`` is the
    optional ``data.placeholder_hint`` so callers can spot which one is
    the "Max inlet pressure" slot at a glance.
    """
    _, _, ws, _, _ = _build_real_services(data_dir)
    items = asyncio.run(ws.list_placeholders(slug))
    if format == "json":
        typer.echo(json.dumps(items, indent=2))
        return
    if format != "text":
        typer.echo(f"unknown --format {format!r} (use 'text' or 'json')", err=True)
        raise typer.Exit(code=2)
    if not items:
        typer.echo("(no placeholders)")
        return
    for it in items:
        hint = f" / {it['hint']}" if it.get("hint") else ""
        typer.echo(f"{it['id']}  [{it['node_type']}] {it['label']!r}{hint}")


@canvas_app.command("create")
def canvas_create(
    slug: str,
    title: str = typer.Option("", "--title"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    parent: str | None = typer.Option(
        None,
        "--parent",
        help=(
            "Reparent the node onto another node (typically an Area "
            "container's id). Triggers a `NodeReparented` event."
        ),
    ),
    unparent: bool = typer.Option(
        False,
        "--unparent",
        help=(
            "Detach the node from its current parent. "
            "Mutually exclusive with --parent."
        ),
    ),
    data: str | None = typer.Option(None, "--data"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Update fields on an existing node. Move-only when only --x and --y given."""
    if parent is not None and unparent:
        typer.echo("--parent and --unparent are mutually exclusive", err=True)
        raise typer.Exit(code=2)
    if parent is not None and parent == node_id:
        typer.echo("node cannot be its own parent", err=True)
        raise typer.Exit(code=2)
    _, _, ws, _, _ = _build_real_services(data_dir)
    fields: dict = {}
    if label is not None:  fields["label"] = label
    if x is not None:      fields["x"] = x
    if y is not None:      fields["y"] = y
    if width is not None:  fields["width"] = width
    if height is not None: fields["height"] = height
    if data is not None:   fields["data"] = _parse_data(data)
    parent_op = parent is not None or unparent
    parent_val = parent if parent is not None else (None if unparent else None)
    if not fields and not parent_op:
        typer.echo("nothing to update - pass at least one field", err=True)
        raise typer.Exit(code=2)

    async def run():
        # Same dispatch rules as the HTTP PATCH route — keeps HTTP / MCP /
        # CLI behaviour identical (per the v2 adapter-parity rule).
        env = None
        state = None
        if set(fields.keys()) == {"x", "y"} and not parent_op:
            state, env = await ws.move_node(slug, node_id, fields["x"], fields["y"])
        elif parent_op and not fields:
            state, env = await ws.reparent_node(slug, node_id, parent_val)
        else:
            if fields:
                state, env = await ws.update_node(slug, node_id, fields)
            if parent_op:
                state, env = await ws.reparent_node(slug, node_id, parent_val)
        assert env is not None and state is not None  # for type narrowing
        return {"event": env.model_dump(), "state": state.get_state()}
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("remove-node")
def canvas_remove_node(
    slug: str,
    node_id: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Remove a single edge by id."""
    _, _, ws, _, _ = _build_real_services(data_dir)

    async def run():
        state, env = await ws.remove_edge(slug, edge_id)
        return {"event": env.model_dump(), "state": state.get_state()}
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("update-edge")
def canvas_update_edge(
    slug: str,
    edge_id: str,
    label: str | None = typer.Option(None, "--label", "-l"),
    edge_type: str | None = typer.Option(None, "--type", "-t", help="`floating` or `anchored`"),
    source_handle: str | None = typer.Option(None, "--source-handle"),
    target_handle: str | None = typer.Option(None, "--target-handle"),
    data: str | None = typer.Option(None, "--data", help="JSON object replacing the edge's `data` field"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Patch an edge's fields (label, type, handles, data)."""
    _, _, ws, _, _ = _build_real_services(data_dir)
    fields: dict = {}
    if label is not None: fields["label"] = label
    if edge_type is not None: fields["edge_type"] = edge_type
    if source_handle is not None: fields["sourceHandle"] = source_handle
    if target_handle is not None: fields["targetHandle"] = target_handle
    if data is not None: fields["data"] = _parse_data(data)
    if not fields:
        typer.echo("nothing to update - pass at least one of --label / --type / --source-handle / --target-handle / --data", err=True)
        raise typer.Exit(code=1)

    async def run():
        state, env = await ws.update_edge(slug, edge_id, fields)
        return {"event": env.model_dump(), "state": state.get_state()}
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@canvas_app.command("clear")
def canvas_clear(
    slug: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm - clear removes EVERY node and edge on the workspace."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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


@canvas_app.command("organize")
def canvas_organize(
    slug: str,
    root_id: str,
    orientation: str = typer.Option(
        "vertical", "--orientation", "-o",
        help="`vertical` (default) or `horizontal`.",
    ),
    algo: str = typer.Option(
        "dagre", "--algo", "-a",
        help="Layout algorithm. Only `dagre` ships today.",
    ),
    direction: str = typer.Option(
        "any", "--direction",
        help=(
            "Edge-walk policy. `outgoing` (parent->child arrows), `incoming` "
            "(reports-to: subordinate->boss arrows), or `any` (undirected, "
            "the default - v1 behaviour). Pick `incoming` on a reports-to "
            "chart to scope strictly to subordinates of <root_id>."
        ),
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Re-lay-out the subtree under <root_id> into a tidy tree.

    Emits one NodeMoved per descendant whose position changes; the root
    itself stays put. Same backend code as the HTTP `POST /layout` route
    and the `canvas_organize_subtree` MCP tool — the adapter parity rule
    means the move list you get here is byte-equal to what the UI would
    produce for the same canvas.
    """
    _, _, ws, _, _ = _build_real_services(data_dir)

    async def run():
        state, envelopes = await ws.organize_subtree(
            slug, root_id,
            orientation=orientation, algo=algo, direction=direction,
        )
        moves = [
            {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
            for env in envelopes
        ]
        return {
            "moves": moves, "event_count": len(envelopes),
            "state": state.get_state(),
        }
    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except ValueError as e:
        typer.echo(f"organize failed: {e}", err=True)
        raise typer.Exit(code=2)


@canvas_app.command("align")
def canvas_align(
    slug: str,
    node_ids: list[str] = typer.Argument(..., help="Node ids to align (at least 2)."),
    anchor: str = typer.Option(
        "top", "--anchor", "-a",
        help="`top` | `bottom` | `left` | `right` | `center-h` | `center-v`.",
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Align the listed nodes to a shared edge or midline.

    Same backend as the HTTP `POST /align` route and the `canvas_align`
    MCP tool — the parity rule means the move list a UI would emit for
    this selection is byte-equal to what we print here.
    """
    _, _, ws, _, _ = _build_real_services(data_dir)

    async def run():
        state, envelopes = await ws.align_nodes(slug, list(node_ids), anchor)  # type: ignore[arg-type]
        moves = [
            {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
            for env in envelopes
        ]
        return {
            "moves": moves, "event_count": len(envelopes),
            "state": state.get_state(),
        }

    from anchor.core.workspace.workspace import CommandError as _CmdErr
    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except _CmdErr as e:
        typer.echo(f"align failed: {e}", err=True)
        raise typer.Exit(code=2)
    except ValueError as e:
        typer.echo(f"align failed: {e}", err=True)
        raise typer.Exit(code=2)


@canvas_app.command("distribute")
def canvas_distribute(
    slug: str,
    node_ids: list[str] = typer.Argument(..., help="Node ids to distribute (at least 3)."),
    axis: str = typer.Option(
        "horizontal", "--axis", "-x",
        help="`horizontal` (default) or `vertical`.",
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Distribute the listed nodes' centres evenly along an axis.

    Endpoints stay put; intermediate nodes get equally-spaced centres.
    Same backend as the HTTP `POST /distribute` route and the
    `canvas_distribute` MCP tool.
    """
    _, _, ws, _, _ = _build_real_services(data_dir)

    async def run():
        state, envelopes = await ws.distribute_nodes(slug, list(node_ids), axis)  # type: ignore[arg-type]
        moves = [
            {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
            for env in envelopes
        ]
        return {
            "moves": moves, "event_count": len(envelopes),
            "state": state.get_state(),
        }

    from anchor.core.workspace.workspace import CommandError as _CmdErr
    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except _CmdErr as e:
        typer.echo(f"distribute failed: {e}", err=True)
        raise typer.Exit(code=2)
    except ValueError as e:
        typer.echo(f"distribute failed: {e}", err=True)
        raise typer.Exit(code=2)


@canvas_app.command("create-sub")
def canvas_create_sub(
    parent_slug: str,
    sub_slug: str,
    title: str = typer.Option("", "--title", "-t"),
    x: float = typer.Option(0.0, "--x"),
    y: float = typer.Option(0.0, "--y"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Create a child canvas <sub_slug> and link it from <parent_slug>.

    Composite of `canvas create` + a `node_type=canvas` linking node so
    the child workspace and the breadcrumb-able link land in one go.
    Same WorkspaceService.create_sub_canvas backing as the
    `POST /sub-canvas` HTTP route and the `canvas_create_sub_canvas`
    MCP tool — adapter parity rule.
    """
    _, _, ws, _, _ = _build_real_services(data_dir)

    async def run():
        return await ws.create_sub_canvas(
            parent_slug, sub_slug, title=title, x=x, y=y,
        )
    try:
        typer.echo(json.dumps(asyncio.run(run()), indent=2))
    except Exception as e:  # noqa: BLE001
        typer.echo(f"create-sub failed: {e}", err=True)
        raise typer.Exit(code=2)


@canvas_app.command("snapshot")
def canvas_snapshot(
    slug: str,
    out: Path | None = typer.Option(None, "--out", "-o", help="Where to write the snapshot. Default: data_dir/snapshots/<slug>/<ts>.png."),
    image_format: str = typer.Option("png", "--format", "-f", help="png (default) or svg."),
    viewport: str | None = typer.Option(None, "--viewport", help="WxH in CSS pixels, e.g. '1920x1080'."),
    full_page: bool = typer.Option(True, "--full-page/--viewport-only", help="Capture the whole document (default) or just the viewport."),
    base_url: str = typer.Option("http://localhost:8002", "--base-url", help="URL of a running `anchor serve`."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Render the named workspace canvas to an image.

    Requires a running `anchor serve` reachable at --base-url. The headless
    chromium navigates to {base_url}/c/{slug} so the same React Flow code
    the user sees in the browser does the rendering.
    """
    vp: tuple[int, int] | None = None
    if viewport is not None:
        try:
            w, h = viewport.lower().split("x")
            vp = (int(w), int(h))
        except (ValueError, IndexError):
            typer.echo(f"--viewport: expected WxH (e.g. 1920x1080), got {viewport!r}", err=True)
            raise typer.Exit(code=2)

    _, _, ws, _, _ = _build_real_services(data_dir, base_url=base_url)

    async def run():
        return await ws.snapshot(slug, format=image_format, viewport=vp, full_page=full_page)

    try:
        result = asyncio.run(run())
    except RuntimeError as e:
        typer.echo(f"snapshot failed: {e}", err=True)
        typer.echo("Hint: ensure `anchor serve --port <p>` is running and pass --base-url http://localhost:<p>.", err=True)
        raise typer.Exit(code=1)
    except (ValueError, NotImplementedError) as e:
        typer.echo(f"snapshot failed: {e}", err=True)
        raise typer.Exit(code=2)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        if result.path is not None:
            out.write_bytes(result.path.read_bytes())
        else:
            assert result.bytes_ is not None
            out.write_bytes(result.bytes_)
        typer.echo(str(out))
        return

    # No --out: print the snapshotter's own path (the timeline file under
    # data_dir/snapshots/<slug>/<ts>.png). For inline-bytes snapshotters
    # there's nothing to print — write a tmp file and surface it.
    if result.path is not None:
        typer.echo(str(result.path))
    else:
        import tempfile
        ext = f".{result.format}"
        tmp = Path(tempfile.NamedTemporaryFile(suffix=ext, delete=False).name)
        assert result.bytes_ is not None
        tmp.write_bytes(result.bytes_)
        typer.echo(str(tmp))


@sysml_app.command("render")
def sysml_render(
    sysml_path: Path = typer.Argument(...),
    workspace_slug: str = typer.Option(..., "--workspace", "-w"),
    x_offset: float = typer.Option(0.0, "--x-offset"),
    y_offset: float = typer.Option(0.0, "--y-offset"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
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
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Export the workspace's SysML elements back to text (Phase 1 stub)."""
    _, bus, workspace, _, _ = _build_real_services(data_dir)
    from anchor.extensions.anchor_sysml import extension as sysml_ext
    svc = sysml_ext.build_service(data_dir, bus, workspace=workspace)

    async def run():
        return await svc.export(workspace_slug=workspace_slug)

    typer.echo(asyncio.run(run()))


# ── FMU subcommands ─────────────────────────────────────────────────────────
#
# Peer to the `fmu.*` MCP tools. Each delegates to the same FmuService
# methods; the architecture's parity rule (see SKILL.md, feedback memory
# `feedback_adapter_parity.md`) demands every op reaches all three
# adapters in the same PR.


def _build_fmu_service(data_dir: Path):
    """Best-effort FMU service for one-shot CLI commands.

    Raises a clean error if neither FMPy nor the ANCHOR_FMU_DEMO=1
    opt-in is available; the FmuRuntimeUnavailableError message tells
    the user how to fix it (install the fmus extra, or set the env var
    if they want the synthetic offline demo).
    """
    try:
        from anchor.extensions.anchor_fmus import extension as fmu_ext
        from anchor.infra.bus.memory_bus import MemoryEventBus
    except ImportError as e:  # pragma: no cover
        typer.echo(f"FMU extension not available: {e}", err=True)
        raise typer.Exit(code=1)
    bus = MemoryEventBus()
    try:
        return fmu_ext.build_service(data_dir, bus)
    except fmu_ext.FmuRuntimeUnavailableError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1)


@fmu_app.command("inspect")
def fmu_inspect(
    fmu_path: Path = typer.Argument(...),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Upload an .fmu and print its parsed model description."""
    if not fmu_path.exists():
        typer.echo(f"FMU not found: {fmu_path}", err=True)
        raise typer.Exit(code=1)
    svc = _build_fmu_service(data_dir)

    async def run():
        return await svc.upload_and_inspect(fmu_path.read_bytes(), fmu_path.name)
    typer.echo(asyncio.run(run()).model_dump_json(indent=2))


@fmu_app.command("list")
def fmu_list(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List every FMU known to this Anchor install."""
    svc = _build_fmu_service(data_dir)

    async def run():
        return [m.model_dump() for m in await svc.list_models()]
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@fmu_app.command("get")
def fmu_get(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Get one FMU's model description by slug."""
    svc = _build_fmu_service(data_dir)

    async def run():
        return await svc.get_model(slug)
    model = asyncio.run(run())
    if model is None:
        typer.echo(f"unknown FMU: {slug}", err=True)
        raise typer.Exit(code=1)
    typer.echo(model.model_dump_json(indent=2))


@fmu_app.command("simulate")
def fmu_simulate(
    slug: str,
    parameters: str | None = typer.Option(None, "--params", help="JSON object of parameter overrides."),
    stop_time: float = typer.Option(1.0, "--stop-time"),
    output_interval: float = typer.Option(0.01, "--output-interval"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Run a simulation. Prints the SimulationRun JSON (includes simulation_id)."""
    overrides: dict | None = None
    if parameters is not None:
        try:
            overrides = json.loads(parameters)
        except json.JSONDecodeError as e:
            typer.echo(f"--params must be a JSON object: {e}", err=True)
            raise typer.Exit(code=2)
    svc = _build_fmu_service(data_dir)

    async def run():
        return await svc.simulate(
            slug, parameter_overrides=overrides,
            stop_time=stop_time, output_interval=output_interval,
        )
    typer.echo(asyncio.run(run()).model_dump_json(indent=2))


@fmu_app.command("results")
def fmu_results(
    simulation_id: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print the time series for a completed simulation."""
    svc = _build_fmu_service(data_dir)

    async def run():
        return await svc.get_series(simulation_id)
    series = asyncio.run(run())
    if series is None:
        typer.echo(f"unknown simulation: {simulation_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(series.model_dump_json(indent=2))


@fmu_app.command("simulations")
def fmu_simulations(
    fmu_slug: str | None = typer.Option(None, "--fmu", help="Filter to one FMU."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List simulation runs, optionally scoped to one FMU."""
    svc = _build_fmu_service(data_dir)

    async def run():
        return [r.model_dump() for r in await svc.list_simulations(fmu_slug)]
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


# ── CAD subcommands ─────────────────────────────────────────────────────────
#
# Peer to the `cad.*` MCP tools. Same CadService methods that HTTP +
# MCP call.


def _build_cad_service(data_dir: Path):
    """Build a CadService with a fresh MemoryEventBus for one-shot CLI calls."""
    from anchor.extensions.anchor_cad import extension as cad_ext
    from anchor.infra.bus.memory_bus import MemoryEventBus
    return cad_ext.build_service(data_dir, MemoryEventBus())


@cad_app.command("inspect")
def cad_inspect(
    cad_path: Path = typer.Argument(...),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Upload a CAD file (STL/OBJ/STEP/glTF/JSCAD/OpenSCAD) and parse its summary."""
    if not cad_path.exists():
        typer.echo(f"CAD file not found: {cad_path}", err=True)
        raise typer.Exit(code=1)
    svc = _build_cad_service(data_dir)

    async def run():
        return await svc.upload_and_inspect(cad_path.read_bytes(), cad_path.name)
    typer.echo(asyncio.run(run()).model_dump_json(indent=2))


@cad_app.command("list")
def cad_list(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List every CAD model known to this Anchor install."""
    svc = _build_cad_service(data_dir)

    async def run():
        return [m.model_dump() for m in await svc.list_models()]
    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@cad_app.command("get")
def cad_get(
    slug: str,
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Get one CAD model's summary by slug."""
    svc = _build_cad_service(data_dir)

    async def run():
        return await svc.get_model(slug)
    model = asyncio.run(run())
    if model is None:
        typer.echo(f"unknown CAD slug: {slug}", err=True)
        raise typer.Exit(code=1)
    typer.echo(model.model_dump_json(indent=2))


@cad_app.command("fetch")
def cad_fetch(
    slug: str,
    copy_to: Path | None = typer.Option(None, "--copy-to"),
    out: str | None = typer.Option(None, "--out", help="Pass '-' to stream the bytes to stdout."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print the on-disk path of the raw CAD file (or stream it with --out -)."""
    svc = _build_cad_service(data_dir)

    async def run():
        return await svc.store.get_cad_path(slug)
    path = asyncio.run(run())
    _emit_bytes(path, copy_to=copy_to, out=out, label=f"{slug} model")


@cad_app.command("set-parameter")
def cad_set_parameter(
    slug: str,
    parameter_name: str,
    value: str = typer.Argument(..., help="Plain string; JSON-parsed if it looks like a number/object."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Tweak a named parameter on a parametric CAD model.

    The value is JSON-parsed when possible (so `42.5` becomes a float and
    `[1,2,3]` becomes a list). Falls back to the raw string otherwise.
    """
    parsed: object = value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        pass  # use the raw string
    svc = _build_cad_service(data_dir)

    async def run():
        return await svc.set_parameter(slug, parameter_name, parsed)
    try:
        model = asyncio.run(run())
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"failed to set parameter: {exc}", err=True)
        raise typer.Exit(code=1)
    typer.echo(model.model_dump_json(indent=2))


# ── First-day demo ──────────────────────────────────────────────────────────
#
# `anchor demo` is the brand-new-user landing. It seeds ~/anchor-data with the
# bundled LKH-5 sample PDF, ingests it (silver + gold if those layers don't
# exist yet), creates a `demo` workspace, and drops one document node plus
# six placeholder spec slots. Then it boots `anchor serve` so the user opens
# the browser and watches their AI harness fill the placeholders in live.
#
# Placeholders carry `data.placeholder: true` and `data.placeholder_hint:
# "<what we want here>"`. The web UI dashes the outline + shows a hint chip;
# the agent calls `canvas_list_placeholders` (parity across HTTP/MCP/CLI) to
# enumerate them, then `search_documents` + `canvas_update_node` to fill.

_DEMO_PLACEHOLDER_HINTS = (
    "Max inlet pressure",
    "Temperature range",
    "Motor power range",
    "Wetted materials",
    "Seal water connection",
    "NPSH",
)

_DEMO_PDF_NAME = "alfa-laval-lkh-centrifugal-pump.pdf"
_DEMO_SLUG = "alfa-laval-lkh-centrifugal-pump"
_DEMO_WORKSPACE = "demo"


def _find_sample_pdf() -> Path | None:
    """Locate the bundled LKH-5 PDF the demo needs.

    Search order:
      1. `v2/data/bronze/<pdf>` — checked-in sample beside the source tree.
      2. `v2/data/samples/<pdf>` — placeholder alt path if we move samples.
      3. anchor wheel's bundled data (when running from `uv tool install`).

    Returns None if nothing is found — the demo then falls back to "seeded
    workspace without a real PDF" so the rest still works."""
    here = Path(__file__).resolve()
    # When installed: parents[2] is `anchor/` package root.
    # When in repo:   parents[4] is `v2/`.
    candidates = [
        here.parents[4] / "data" / "bronze" / _DEMO_PDF_NAME,
        here.parents[4] / "data" / "samples" / _DEMO_PDF_NAME,
        here.parents[2] / "_samples" / _DEMO_PDF_NAME,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


@app.command()
def demo(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    port: int = typer.Option(8002, "--port", "-p"),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind address; loopback by default (see `anchor serve --help`).",
    ),
    no_serve: bool = typer.Option(
        False, "--no-serve",
        help="Skip the `anchor serve` boot at the end (useful for CI / smoke).",
    ),
) -> None:
    """One-shot first-day setup. Ingests the bundled LKH-5 PDF, seeds a `demo`
    workspace with one document node + six placeholder spec slots, then runs
    `anchor serve`.

    Idempotent: re-running won't re-ingest a doc that's already silvered, and
    won't duplicate the document or placeholder nodes on the demo canvas.
    """
    import shutil

    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "bronze").mkdir(parents=True, exist_ok=True)

    # 1. Stage the bundled PDF into bronze so the user can re-ingest from
    # the same path agents would see via `list_documents`.
    target_pdf = data_dir / "bronze" / _DEMO_PDF_NAME
    if not target_pdf.exists():
        src = _find_sample_pdf()
        if src is not None:
            shutil.copyfile(src, target_pdf)
            typer.echo(f"[demo] staged sample PDF -> {target_pdf}")
        else:
            typer.echo(
                "[demo] bundled LKH-5 PDF not found in this install; "
                "the demo workspace will be created without an ingested doc.",
            )

    config, _, ws, ingest_svc, doc_store = _build_real_services(
        data_dir, base_url=f"http://localhost:{port}",
    )

    async def setup() -> dict[str, Any]:
        # 2. Ingest the sample if it hasn't been silvered yet.
        docs = await doc_store.list_documents()
        existing = {d["slug"] for d in docs}
        if target_pdf.exists() and _DEMO_SLUG not in existing:
            typer.echo(f"[demo] ingesting {_DEMO_PDF_NAME} (silver + gold)...")
            await ingest_svc.ingest_pdf(
                target_pdf.read_bytes(), _DEMO_PDF_NAME,
                polish=True, regions=True,
                polish_model=config.polish_model,
                region_model=config.region_model,
                dpi=config.dpi,
            )
        elif _DEMO_SLUG in existing:
            typer.echo(f"[demo] {_DEMO_SLUG} already ingested - skipping")

        # 3. Create the `demo` workspace if missing. The store auto-creates
        # on `.load()`, so check `list_workspaces` instead — that doesn't
        # touch disk for slugs that don't exist.
        existing_ws = {w["slug"] for w in await ws.list_workspaces()}
        created_ws = False
        if _DEMO_WORKSPACE not in existing_ws:
            await ws.create_workspace(_DEMO_WORKSPACE, title="Demo workspace")
            typer.echo(f"[demo] created workspace {_DEMO_WORKSPACE!r}")
            created_ws = True

        # 4. Snapshot current canvas and only add nodes if missing. The
        # check is intentionally lax (label match) so the user can edit
        # them freely without re-running creating dupes.
        state = await ws.get_state(_DEMO_WORKSPACE)
        existing_labels = {(n.get("node_type"), n.get("label")) for n in state.get("nodes", [])}
        # Document node
        if ("document", "Alfa Laval LKH-5") not in existing_labels and _DEMO_SLUG in {
            d["slug"] for d in await doc_store.list_documents()
        }:
            doc_meta = next(
                (d for d in await doc_store.list_documents() if d["slug"] == _DEMO_SLUG), None,
            )
            await ws.add_node(
                _DEMO_WORKSPACE,
                node_type="document",
                label="Alfa Laval LKH-5",
                x=120.0, y=180.0,
                data={
                    "slug": _DEMO_SLUG,
                    "filename": _DEMO_PDF_NAME,
                    "status": "ready",
                    "page_count": (doc_meta or {}).get("page_count", 4),
                },
            )
        # Placeholder spec nodes — six, laid out in a 2-column grid right
        # of the document node so the user immediately sees the shape.
        col_x = (480.0, 760.0)
        row_y_start = 60.0
        row_dy = 130.0
        for i, hint in enumerate(_DEMO_PLACEHOLDER_HINTS):
            if ("spec", hint) in existing_labels:
                continue
            await ws.add_node(
                _DEMO_WORKSPACE,
                node_type="spec",
                label=hint,
                x=col_x[i % 2],
                y=row_y_start + (i // 2) * row_dy,
                data={
                    "placeholder": True,
                    "placeholder_hint": hint,
                    "rows": [],
                },
            )

        final = await ws.get_state(_DEMO_WORKSPACE)
        return {
            "workspace": _DEMO_WORKSPACE,
            "node_count": len(final.get("nodes", [])),
            "created_workspace": created_ws,
        }

    summary = asyncio.run(setup())

    canvas_url = f"http://localhost:{port}/c/{_DEMO_WORKSPACE}"
    typer.echo("")
    typer.echo("-" * 60)
    typer.echo("  Anchor demo is ready.")
    typer.echo("-" * 60)
    typer.echo(f"  Workspace        : {summary['workspace']}  ({summary['node_count']} nodes)")
    typer.echo(f"  Canvas URL       : {canvas_url}")
    typer.echo(f"  Data dir         : {data_dir}")
    typer.echo("")
    typer.echo("  Register Anchor with your AI harness:")
    typer.echo("    anchor install claude-code           # or `cursor`")
    typer.echo("")
    typer.echo("  Then in your agent, paste:")
    typer.echo(
        '    "Please fill in the placeholder spec nodes on the `demo` '
        'canvas using `canvas_list_placeholders` + `search_documents`."',
    )
    typer.echo("-" * 60)

    if no_serve:
        typer.echo("[demo] --no-serve set; not booting the server.")
        return

    typer.echo("")
    typer.echo(f"[demo] starting `anchor serve` on {host}:{port}...")
    # Delegate to the existing `serve` command implementation rather than
    # re-wiring everything. Use the same parameter contract so users can
    # later switch to plain `anchor serve` and get the same env.
    serve(data_dir=data_dir, host=host, port=port)


@app.command()
def version() -> None:
    """Print the installed Anchor version."""
    from anchor import __version__
    typer.echo(__version__)


if __name__ == "__main__":
    app()
