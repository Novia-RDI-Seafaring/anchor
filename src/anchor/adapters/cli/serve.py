"""Root ``anchor serve`` command."""

from __future__ import annotations

import socket
from pathlib import Path

import typer

from anchor.adapters.project_runtime import (
    RuntimeProfile,
    build_project_runtime_for_data_dir,
)


def _find_free_port(host: str, start: int, *, limit: int = 20) -> int:
    """First bindable port at or after `start`. Raises OSError if none in range."""
    for candidate in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, candidate))
                return candidate
            except OSError:
                continue
    raise OSError(f"no free port in {start}..{start + limit - 1}")


def _migrate_bbox_origin(runtime) -> None:
    """Flip legacy bottom-left bboxes to top-left before serving (#281)."""
    import asyncio

    from anchor.extensions.anchor_pdfs.core.bbox_migration import migrate_all

    try:
        renderer = getattr(runtime.ingest, "renderer", None)
        report = asyncio.run(migrate_all(runtime.doc_store, renderer, runtime.workspace))
    except Exception as exc:  # noqa: BLE001 - never block serving on a migration hiccup
        typer.echo(f"[anchor serve] bbox migration skipped: {exc}", err=True)
        return
    if report.get("migrated"):
        typer.echo(
            f"[anchor serve] migrated {len(report['migrated'])} document(s) to top-left "
            f"bboxes (#281): {', '.join(report['migrated'])}",
            err=True,
        )
    for item in report.get("skipped", []):
        typer.echo(
            f"[anchor serve] bbox migration skipped {item['slug']}: {item.get('reason')} "
            "(run `anchor migrate bbox-origin` once the PDF is available)",
            err=True,
        )


def _warn_fmu_for_serve(exc: Exception) -> None:
    if exc.__class__.__name__ == "FmuRuntimeUnavailableError":
        typer.echo(f"Warning: FMU extension disabled: {exc}", err=True)
    else:
        typer.echo(f"Warning: FMU extension failed to start: {exc}", err=True)


def serve(
    data_dir: Path = typer.Option(
        None, "--data-dir", "-d", help="Explicit storage dir (overrides --env/--project)."
    ),
    env: str = typer.Option(None, "--env", help="Environment to serve (default: resolved)."),
    project: str = typer.Option(
        None, "--project", help="Project to serve (default: the environment's default)."
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help=(
            "Bind address. Defaults to 127.0.0.1 (loopback) because the HTTP "
            "server is unauthenticated. Pass --host 0.0.0.0 to expose to "
            "your LAN - you are responsible for fronting it with auth."
        ),
    ),
    port: int = typer.Option(
        8002, "--port", "-p", help="Preferred port; if taken, the next free port is used."
    ),
) -> None:
    """Run the HTTP adapter (FastAPI + SSE) and serve the frontend bundle."""
    import uvicorn

    from anchor.adapters.http.app import build_app

    # Resolve the project to serve from --env/--project unless an explicit
    # --data-dir was given. One server serves one project (a browser session is
    # one project); point it at a non-default project with --project.
    if data_dir is None:
        from anchor.infra.environment import resolve_project

        rp = resolve_project(env, project)
        data_dir = rp.data_dir
        typer.echo(f"[anchor serve] env={rp.environment.name} project={rp.name}", err=True)

    # If the requested port is taken (e.g. another `anchor serve` for a
    # different project), fall through to the next free one rather than failing
    # to bind. Resolve before base_url so the snapshotter loops back to *this*
    # server's actual port.
    requested_port = port
    try:
        port = _find_free_port(host, port)
    except OSError as exc:
        typer.echo(f"[anchor serve] {exc}", err=True)
        raise typer.Exit(code=1) from None

    # The snapshotter points at the same server we're about to start so
    # snapshots taken via CLI / MCP loop back to this process.
    base_url = f"http://localhost:{port}"
    runtime = build_project_runtime_for_data_dir(
        data_dir,
        profile=RuntimeProfile.FULL,
        base_url=base_url,
        fmu_warning=_warn_fmu_for_serve,
    )
    config = runtime.config
    data_dir = config.data_dir
    static_dir = Path(__file__).resolve().parents[2] / "_web_dist"
    if not static_dir.is_dir():
        # development: walk up to web/dist in the repository checkout
        static_dir = Path(__file__).resolve().parents[4] / "web" / "dist"

    # Self-correct legacy data (#281): flip any bottom-left silver/gold/canvas
    # bboxes to top-left once, before serving. Idempotent and cheap on an
    # already-migrated project; a document whose page sizes are unavailable is
    # reported and left untouched rather than half-flipped.
    _migrate_bbox_origin(runtime)

    app_ = build_app(runtime, static_dir=static_dir if static_dir.is_dir() else None)

    # Self-identification surface (#177, #179): record this server's actual
    # binding so /api/whoami, the MCP server_info tool, and `anchor serve-info`
    # can report which project lives on which port -- and so `canvas url`
    # resolves against a server really serving this data dir instead of
    # guessing :8002.
    from datetime import UTC, datetime

    from anchor.infra import serve_registry

    started_at = datetime.now(UTC).isoformat()
    env_name, project_name = serve_registry.identify_data_dir(data_dir)
    app_.state.serve_binding = {
        "host": host,
        "port": port,
        "data_dir": str(data_dir),
        "env": env_name,
        "project": project_name,
        "started_at": started_at,
    }
    record_path = None
    try:
        record_path = serve_registry.register_serve(
            host=host, port=port, data_dir=data_dir, started_at=started_at
        )
    except OSError as exc:  # advisory only -- never block the server from booting
        typer.echo(f"[anchor serve] could not write serve record: {exc}", err=True)

    if port != requested_port:
        typer.echo(
            f"[anchor serve] port {requested_port} is in use -- serving on {port} instead.",
            err=True,
        )
    typer.echo(f"[anchor serve] data_dir={data_dir}  ->  http://{host}:{port}")
    try:
        uvicorn.run(app_, host=host, port=port)
    finally:
        serve_registry.unregister_serve(record_path)
