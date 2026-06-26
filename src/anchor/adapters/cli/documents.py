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
    force: bool = typer.Option(
        False, "--force", help="Re-ingest even if the slug already has gold (overwrites it)."
    ),
) -> None:
    """Run a PDF through the bronze -> silver -> gold pipeline.

    Idempotent by default: if the slug is already gold-extracted it is skipped.
    Pass ``--force`` to recompute and overwrite (re-runs the billed gold stage).
    """
    if not pdf_path.exists():
        typer.echo(f"PDF not found: {pdf_path}", err=True)
        raise typer.Exit(code=1)
    # A clean run is now quiet (docling/OCR noise is suppressed), so say what is
    # happening — a multi-page extract can take ~30s and should not look hung.
    typer.echo(
        f"Ingesting {pdf_path.name} … bronze (layout + OCR) → silver (pages) → gold (regions)",
        err=True,
    )
    config, _, _, ingest_svc, _ = _build_real_services(data_dir)

    async def run() -> dict:
        return await ingest_svc.ingest_pdf(
            pdf_path.read_bytes(),
            pdf_path.name,
            polish=not skip_polish,
            regions=not skip_regions,
            force=force,
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


def ingests(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List ingests in flight for this project (any trigger: CLI, MCP, UI).

    Reads the durable per-slug activity records, so an ingest running in
    another process (or left behind by a crash) still shows up here. Each
    entry carries its current stage, progress, and terminal state.
    """
    from anchor.core.clock import SystemClock
    from anchor.extensions.anchor_pdfs.core.ingest_activity import IngestActivityRegistry

    _, _, _, _, doc_store = _build_real_services(data_dir)
    registry = IngestActivityRegistry(store=doc_store, _now=SystemClock().now)
    activities = asyncio.run(registry.snapshot())
    typer.echo(json.dumps({"ingests": [a.to_dict() for a in activities]}, indent=2))


def ingest_status(
    slug: str = typer.Argument(..., help="Document slug to report on."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Show the live ingest-activity record for one document slug.

    Reports the current stage, progress, and terminal state (done / failed +
    failed stage). Exits 1 (with {found: false}) when nothing is ingesting or
    has recently ingested that slug.
    """
    from anchor.core.clock import SystemClock
    from anchor.extensions.anchor_pdfs.core.ingest_activity import IngestActivityRegistry

    _, _, _, _, doc_store = _build_real_services(data_dir)
    registry = IngestActivityRegistry(store=doc_store, _now=SystemClock().now)
    activity = asyncio.run(registry.get(slug))
    if activity is None:
        typer.echo(json.dumps({"slug": slug, "found": False}, indent=2))
        raise typer.Exit(code=1)
    typer.echo(json.dumps({"found": True, **activity.to_dict()}, indent=2))


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


def derive_region(
    slug: str = typer.Argument(..., help="Document slug."),
    parent_region_id: str = typer.Argument(..., help="Region id the new region derives from."),
    region: str = typer.Option(
        ..., "--region", help="The derived region as a JSON string, or @path to a JSON file."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Persist a region derived from an existing gold region.

    The consumer side of an OIP region producer: inherits the parent's
    source_ref (provenance) and records derived_from, then stores it durably.
    Re-run `anchor embed <slug>` to make the new region searchable.
    """
    raw = Path(region[1:]).read_text(encoding="utf-8") if region.startswith("@") else region
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"--region is not valid JSON: {exc}", err=True)
        raise typer.Exit(code=1) from None
    _, _, _, ingest_svc, _ = _build_real_services(data_dir)
    try:
        out = asyncio.run(ingest_svc.derive_region(slug, parent_region_id, payload))
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(out, indent=2))


def extract(
    slug: str = typer.Argument(..., help="Document slug to extract from."),
    shape: Path = typer.Option(
        ..., "--shape", help="Path to the shape JSON (by-example or JSON Schema)."
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write the result JSON here instead of stdout."
    ),
    regions: list[str] = typer.Option(
        None, "--region", help="Select a region, e.g. 'p2/r4' (repeatable)."
    ),
    pages: list[int] = typer.Option(
        None, "--page", "-p", help="Select all regions on a page (repeatable)."
    ),
    entity: str | None = typer.Option(
        None, "--entity", "-e", help="Select regions scoped to an entity, e.g. 'LKH-5'."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Pointed extraction: selected regions/entities into a caller shape (#132).

    Resolves the selection (regions / pages / entity; empty selects every gold
    region) and fills the shape from the selected regions' cells, attaching a
    `source_ref` provenance entry per filled leaf. Unfillable leaves are listed
    in `unfilled` and never guessed. Prints `{doc_slug, data, provenance,
    unfilled}` (or writes it to --output).
    """
    if not shape.exists():
        typer.echo(f"shape file not found: {shape}", err=True)
        raise typer.Exit(code=1)
    try:
        shape_obj = json.loads(shape.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        typer.echo(f"--shape is not valid JSON: {exc}", err=True)
        raise typer.Exit(code=1) from None

    select: dict = {}
    if regions:
        select["regions"] = list(regions)
    if pages:
        select["pages"] = list(pages)
    if entity:
        select["entity"] = entity

    from anchor.extensions.anchor_pdfs.core.pointed_extraction import (
        PointedExtractionError,
    )

    _, _, _, ingest_svc, _ = _build_real_services(data_dir)
    try:
        result = asyncio.run(
            ingest_svc.extract_pointed(slug, select=select or None, shape=shape_obj)
        )
    except PointedExtractionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    payload = json.dumps(result, indent=2)
    if output is None:
        typer.echo(payload)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        typer.echo(str(output))


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
    page_pos: int | None = typer.Argument(
        None,
        help="Page number to filter (positional form, same as --page).",
        show_default=False,
    ),
    page: int | None = typer.Option(None, "--page", "-p", help="Page number to filter (option form)."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print gold regions for a document, optionally filtered to a page.

    The page can be supplied as a positional argument or via --page/-p.
    Both forms are equivalent: ``anchor regions SLUG PAGE`` and
    ``anchor regions SLUG --page PAGE`` do the same thing.
    """
    if page_pos is not None and page is not None:
        typer.echo("error: supply page as a positional argument or --page, not both", err=True)
        raise typer.Exit(code=2)
    effective_page = page if page is not None else page_pos
    _, _, _, _, doc_store = _build_real_services(data_dir)
    typer.echo(json.dumps(asyncio.run(doc_store.get_regions(slug, page=effective_page)), indent=2))


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
    page_pos: int | None = typer.Argument(
        None,
        help="Page number (positional form, same as --page).",
        show_default=False,
    ),
    page: int | None = typer.Option(None, "--page", "-p", help="Page number (option form)."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print polished or raw markdown for a page.

    The page can be supplied as a positional argument or via --page/-p.
    Both forms are equivalent: ``anchor page-text SLUG PAGE`` and
    ``anchor page-text SLUG --page PAGE`` do the same thing.
    """
    if page_pos is not None and page is not None:
        typer.echo("error: supply page as a positional argument or --page, not both", err=True)
        raise typer.Exit(code=2)
    effective_page = page if page is not None else page_pos
    if effective_page is None:
        typer.echo("error: page is required (positional or --page/-p)", err=True)
        raise typer.Exit(code=2)
    _, _, _, _, doc_store = _build_real_services(data_dir)
    text = asyncio.run(doc_store.get_page_text(slug, effective_page))
    if text is None:
        typer.echo(f"no text for {slug}:{effective_page}", err=True)
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
    page_pos: int | None = typer.Argument(
        None,
        help="Page number (positional form, same as --page).",
        show_default=False,
    ),
    page: int | None = typer.Option(None, "--page", "-p", help="Page number (option form)."),
    copy_to: Path | None = typer.Option(None, "--copy-to"),
    out: str | None = typer.Option(None, "--out", help="Pass '-' to stream the bytes to stdout."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Page screenshot. Prints the path by default; --copy-to or --out - for the bytes.

    The page can be supplied as a positional argument or via --page/-p.
    Both forms are equivalent: ``anchor page-image SLUG PAGE`` and
    ``anchor page-image SLUG --page PAGE`` do the same thing.
    """
    if page_pos is not None and page is not None:
        typer.echo("error: supply page as a positional argument or --page, not both", err=True)
        raise typer.Exit(code=2)
    effective_page = page if page is not None else page_pos
    if effective_page is None:
        typer.echo("error: page is required (positional or --page/-p)", err=True)
        raise typer.Exit(code=2)
    _, _, _, _, doc_store = _build_real_services(data_dir)
    path = asyncio.run(doc_store.get_page_image_path(slug, effective_page))
    _emit_bytes(path, copy_to=copy_to, out=out, label=f"{slug} page {effective_page}")


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
            output.write_text(md, encoding="utf-8")
            typer.echo(str(output))
        return
    typer.echo(f"unknown --format {format!r} (use json | pdf | md)", err=True)
    raise typer.Exit(code=2)


def register_document_commands(app: typer.Typer) -> None:
    """Attach root document commands without changing their public names."""
    app.command()(ingest)
    app.command("list")(list_documents)
    app.command("ingests")(ingests)
    app.command("ingest-status")(ingest_status)
    app.command()(search)
    app.command("derive-region")(derive_region)
    app.command()(extract)
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
