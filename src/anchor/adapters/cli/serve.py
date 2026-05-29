"""Root ``anchor serve`` command."""

from __future__ import annotations

from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.services import _build_real_services


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
        # development: walk up to web/dist in the repository checkout
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
        MarpSynopsisRenderer,
        PymupdfSynopsisRenderer,
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
