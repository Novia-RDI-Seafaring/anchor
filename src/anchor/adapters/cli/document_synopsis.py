"""Synopsis presentation command for the document CLI."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.services import _build_real_services


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

    ``--format json`` prints SynopsisData to stdout. The ``pdf`` and ``md``
    formats write presentation artifacts when an output path is supplied.
    """
    _, _, _, _, doc_store = _build_real_services(data_dir)

    # Keep renderer imports command-local so unrelated CLI commands do not
    # load optional PDF presentation dependencies during startup.
    from anchor.extensions.anchor_pdfs.core.services import SynopsisService
    from anchor.extensions.anchor_pdfs.infra.synopsis_renderers import (
        MarpSynopsisRenderer,
        PymupdfSynopsisRenderer,
    )

    service = SynopsisService(
        doc_store,
        pdf_renderer=PymupdfSynopsisRenderer(),
        md_renderer=MarpSynopsisRenderer(),
    )

    if format == "json":

        async def compose_json():
            return asdict(await service.compose(slug=slug, entity=entity))

        typer.echo(json.dumps(asyncio.run(compose_json()), indent=2))
        return
    if format == "pdf":

        async def render_pdf():
            return await service.render_pdf(slug=slug, entity=entity)

        pdf_bytes = asyncio.run(render_pdf())
        output = output or Path(f"{slug}-{entity}.pdf")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(pdf_bytes)
        typer.echo(str(output))
        return
    if format == "md":

        async def render_markdown():
            return await service.render_markdown(
                slug=slug,
                entity=entity,
                crop_url_base=crop_url_base,
            )

        markdown = asyncio.run(render_markdown())
        if output is None:
            typer.echo(markdown)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(markdown, encoding="utf-8")
            typer.echo(str(output))
        return
    typer.echo(f"unknown --format {format!r} (use json | pdf | md)", err=True)
    raise typer.Exit(code=2)
