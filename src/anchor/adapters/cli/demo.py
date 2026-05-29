"""Root ``anchor demo`` command."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.serve import serve
from anchor.adapters.cli.services import _build_real_services

# ── First-day demo ──────────────────────────────────────────────────────────
#
# `anchor demo` is the brand-new-user landing. It creates a `demo` workspace
# with six placeholder spec slots, optionally ingests a locally available
# sample PDF, and boots `anchor serve` so the user can fill placeholders from
# their own ingested document.
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
    """Locate an optional local LKH-5 PDF for the demo.

    Search order:
      1. Repository-local `data/bronze/<pdf>`.
      2. Repository-local `data/samples/<pdf>`.
      3. Packaged sample data, if a downstream distribution provides it.

    Returns None if nothing is found — the demo then falls back to "seeded
    workspace without a real PDF" so the rest still works."""
    here = Path(__file__).resolve()
    # When installed: parents[2] is `anchor/` package root.
    # When in repo:   parents[4] is the repository root.
    candidates = [
        here.parents[4] / "data" / "bronze" / _DEMO_PDF_NAME,
        here.parents[4] / "data" / "samples" / _DEMO_PDF_NAME,
        here.parents[2] / "_samples" / _DEMO_PDF_NAME,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def demo(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
    port: int = typer.Option(8002, "--port", "-p"),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind address; loopback by default (see `anchor serve --help`).",
    ),
    no_serve: bool = typer.Option(
        False,
        "--no-serve",
        help="Skip the `anchor serve` boot at the end (useful for CI / smoke).",
    ),
) -> None:
    """One-shot first-day setup. Seeds a `demo` workspace with six placeholder
    spec slots, optionally ingests an available local sample PDF, then runs
    `anchor serve`.

    Idempotent: re-running won't re-ingest a doc that's already silvered, and
    won't duplicate the document or placeholder nodes on the demo canvas.
    """
    import shutil

    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "bronze").mkdir(parents=True, exist_ok=True)

    # 1. Stage an optional local PDF into bronze so the user can re-ingest from
    # the same path agents would see via `list_documents`.
    target_pdf = data_dir / "bronze" / _DEMO_PDF_NAME
    if not target_pdf.exists():
        src = _find_sample_pdf()
        if src is not None:
            shutil.copyfile(src, target_pdf)
            typer.echo(f"[demo] staged sample PDF -> {target_pdf}")
        else:
            typer.echo(
                "[demo] optional LKH-5 PDF not found; the demo workspace will "
                "be created without an ingested document. Use `anchor ingest "
                "/path/to/datasheet.pdf` to add your own.",
            )

    config, _, ws, ingest_svc, doc_store = _build_real_services(
        data_dir,
        base_url=f"http://localhost:{port}",
    )

    async def setup() -> dict[str, Any]:
        # 2. Ingest the sample if it hasn't been silvered yet.
        docs = await doc_store.list_documents()
        existing = {d["slug"] for d in docs}
        if target_pdf.exists() and _DEMO_SLUG not in existing:
            typer.echo(f"[demo] ingesting {_DEMO_PDF_NAME} (silver + gold)...")
            await ingest_svc.ingest_pdf(
                target_pdf.read_bytes(),
                _DEMO_PDF_NAME,
                polish=True,
                regions=True,
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
                (d for d in await doc_store.list_documents() if d["slug"] == _DEMO_SLUG),
                None,
            )
            await ws.add_node(
                _DEMO_WORKSPACE,
                node_type="document",
                label="Alfa Laval LKH-5",
                x=120.0,
                y=180.0,
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
