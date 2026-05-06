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
app.add_typer(canvas_app, name="canvas")
app.add_typer(install_app, name="install")
app.add_typer(extensions_app, name="extensions")


def _build_real_services(data_dir: Path):
    """Wire concrete adapters. Polish/region-extract are OpenAI-only and become
    no-ops if the user hasn't provided ANCHOR_OPENAI_API_KEY — silver still
    builds, gold simply skips. Embeddings default to a local sentence-
    transformer model; OpenAI is opt-in via ANCHOR_OPENAI_API_KEY."""
    from anchor.extensions.anchor_pdfs.core.services import IngestService
    from anchor.core.services.workspace_service import WorkspaceService
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from anchor.infra.config import AnchorConfig
    from anchor.extensions.anchor_pdfs.infra.llm.openai_md_polisher import OpenAIPageMdPolisher
    from anchor.extensions.anchor_pdfs.infra.llm.openai_region_extractor import OpenAIRegionExtractor
    from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
    from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore

    import os

    config = AnchorConfig(data_dir=data_dir)
    bus = MemoryEventBus()
    workspace_store = FsWorkspaceStore(config.canvases_dir)
    doc_store = FsDocStore(config.data_dir)
    workspace = WorkspaceService(workspace_store, bus)
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

    _, bus, workspace, ingest, doc_store = _build_real_services(data_dir)
    static_dir = Path(__file__).resolve().parents[2] / "_web_dist"
    if not static_dir.is_dir():
        # development: walk up to v2/web/dist
        static_dir = Path(__file__).resolve().parents[4] / "web" / "dist"

    # Wire the CAD extension service. Manifest already lives in
    # _bundled_producers; the service handles ingestion and storage.
    from anchor.extensions.anchor_cad import extension as cad_ext
    cad_service = cad_ext.build_service(data_dir, bus)

    app_ = build_app(
        workspace_service=workspace,
        ingest_service=ingest,
        doc_store=doc_store,
        bus=bus,
        static_dir=static_dir if static_dir.is_dir() else None,
        cad_service=cad_service,
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


@app.command()
def version() -> None:
    """Print the installed Anchor version."""
    from anchor import __version__
    typer.echo(__version__)


if __name__ == "__main__":
    app()
