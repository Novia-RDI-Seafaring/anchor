"""Root document commands for the ``anchor`` CLI."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR, _emit_bytes
from anchor.adapters.cli.services import _build_real_services


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
            pdf_path.read_bytes(),
            pdf_path.name,
            polish=not skip_polish,
            regions=not skip_regions,
            polish_model=config.polish_model,
            region_model=config.region_model,
            dpi=config.dpi,
        )

    try:
        result = asyncio.run(run())
    except Exception as exc:  # noqa: BLE001 - surface a clean line, not a stack
        typer.echo(f"Ingest failed for {pdf_path.name}: {exc}", err=True)
        if "MPS" in str(exc) or "float64" in str(exc):
            typer.echo(
                "Hint: this looks like a docling accelerator issue. Set "
                "ANCHOR_DOCLING_DEVICE=cpu and retry.",
                err=True,
            )
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(result, indent=2))


def list_documents(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List all ingested documents."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(doc_store.list_documents()), indent=2))


def search(
    query: str = typer.Argument(..., help="Free-text query."),
    k: int = typer.Option(10, "--k", "-k", help="Top-k hits to return."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Semantic search across every gold-extracted, embedded document.

    Returns top-k grounded hits with (slug, page, region_id, text, score)
    plus skipped documents whose stored embed_model does not match.
    Requires that documents have been embedded first via `anchor embed`.
    """
    _, _, _, ingest_svc, _ = _build_real_services(data_dir)
    if ingest_svc.embedder is None:
        typer.echo(
            "no embedder wired - install sentence-transformers (uv add sentence-transformers)",
            err=True,
        )
        raise typer.Exit(code=1)
    out = asyncio.run(ingest_svc.search(query, k=k))
    typer.echo(json.dumps(out, indent=2))


def embed(
    slug: str | None = typer.Argument(
        None,
        help="Single doc slug; omit to embed all gold-extracted docs that don't have embeddings yet.",
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Re-embed even if embeddings.json already exists."
    ),
) -> None:
    """Embed gold regions of a document and persist to embeddings.json.

    Uses the local sentence-transformer embedder (BAAI/bge-small-en-v1.5
    by default). Auto-runs at the end of `anchor ingest`; this command
    backfills already-ingested docs without re-running the full pipeline.
    """
    _, _, _, ingest_svc, doc_store = _build_real_services(data_dir)
    if ingest_svc.embedder is None:
        typer.echo(
            "no embedder wired - install sentence-transformers (uv add sentence-transformers)",
            err=True,
        )
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
                out.append(
                    {
                        "slug": s,
                        "skipped": True,
                        "reason": "already embedded",
                        "embed_model": existing.get("embed_model"),
                    }
                )
                continue
            n = await ingest_svc.embed_document(s)
            out.append({"slug": s, "embedded": n, "embed_model": ingest_svc.embed_model_id})
        return out

    typer.echo(json.dumps(asyncio.run(run_all()), indent=2))


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


def regions(
    slug: str,
    page: int | None = typer.Option(None, "--page", "-p"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print gold regions for a document, optionally filtered to a page."""
    _, _, _, _, doc_store = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(doc_store.get_regions(slug, page=page)), indent=2))


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
    typer.echo(
        json.dumps(
            {
                "slug": slug,
                "embed_model": data.get("embed_model"),
                "dim": data.get("dim"),
                "embedded_at": data.get("embedded_at"),
                "vector_count": len(data.get("vectors", [])),
            },
            indent=2,
        )
    )


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


def synopsis(
    slug: str,
    entity: str = typer.Option(..., "--entity", "-e", help="e.g. 'LKH-5'"),
    format: str = typer.Option("json", "--format", "-f", help="json | pdf | md"),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write artefact to this path (for pdf/md)."
    ),
    crop_url_base: str | None = typer.Option(
        None, "--crop-url-base", help="(md only) URL prefix for crop references."
    ),
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
        MarpSynopsisRenderer,
        PymupdfSynopsisRenderer,
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


def register_document_commands(app: typer.Typer) -> None:
    """Attach root document commands without changing their public names."""
    app.command()(ingest)
    app.command("list")(list_documents)
    app.command()(search)
    app.command()(embed)
    app.command()(index)
    app.command()(regions)
    app.command("embeddings-meta")(embeddings_meta)
    app.command("page-text")(page_text)
    app.command("gold-map")(gold_map)
    app.command("page-image")(page_image)
    app.command("crop")(crop)
    app.command("pdf")(pdf)
    app.command("synopsis")(synopsis)
