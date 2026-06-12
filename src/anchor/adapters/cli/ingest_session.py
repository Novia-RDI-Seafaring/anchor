"""``anchor ingest-session`` - drive the harness ingestion protocol from a shell.

JSON in, JSON out, so any shell-capable harness (Codex CLI, a script
wrapping a model, a human with jq) can run the same protocol the MCP
tools expose:

    anchor ingest-session begin doc.pdf
    anchor ingest-session get-page <session> 3
    anchor ingest-session submit-page <session> 3 --file page3.json
    anchor ingest-session status --slug doc
    anchor ingest-session finalize <session> --declared-model <id>
    anchor ingest-session abort <session>
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.adapters.cli.services import _build_session_services

ingest_session_app = typer.Typer(
    help="Harness-driven ingestion: you (the agent) polish pages and group "
    "regions; ANCHOR validates, stages, and publishes atomically. No API key needed."
)


def _echo_json(payload: dict) -> None:
    typer.echo(json.dumps(payload, indent=2))


def _exit_on_error(payload: dict) -> None:
    if "error" in payload:
        _echo_json(payload)
        raise typer.Exit(code=1)


@ingest_session_app.command()
def begin(
    pdf_path: Path = typer.Argument(..., help="PDF to ingest."),
    slug: str = typer.Option(None, "--slug", help="Document slug (defaults to the filename)."),
    dpi: int = typer.Option(None, "--dpi", help="Page render DPI."),
    force: bool = typer.Option(False, "--force", help="Re-ingest published gold / restart an open session."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Run the mechanical front half and print the work order."""
    if not pdf_path.exists():
        typer.echo(f"PDF not found: {pdf_path}", err=True)
        raise typer.Exit(code=1)
    _, svc = _build_session_services(data_dir)
    typer.echo(
        f"Preparing {pdf_path.name} ... bronze (layout + OCR) -> silver (pages, candidates)",
        err=True,
    )
    order = asyncio.run(svc.ingest_begin(
        pdf_path.read_bytes(), pdf_path.name, slug=slug, dpi=dpi, force=force,
    ))
    _echo_json(order)


@ingest_session_app.command("get-page")
def get_page(
    session_id: str = typer.Argument(...),
    page: int = typer.Argument(...),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print the work item for one page (image path, raw markdown, candidates)."""
    _, svc = _build_session_services(data_dir)
    item = asyncio.run(svc.ingest_get_page(session_id, page))
    _exit_on_error(item)
    _echo_json(item)


@ingest_session_app.command("submit-page")
def submit_page(
    session_id: str = typer.Argument(...),
    page: int = typer.Argument(...),
    file: Path = typer.Option(
        None, "--file", "-f",
        help="JSON submission: a list of regions, or "
        '{"regions": [...], "polished_md": "..."}. Omit to read stdin.',
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Submit one page's regions (+ optional polished markdown) to staging.

    Exits non-zero when the submission is rejected; the printed errors name
    the fields to repair, then resubmit (resubmitting a page replaces it).
    """
    raw = file.read_text(encoding="utf-8") if file is not None else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"submission is not valid JSON: {exc}", err=True)
        raise typer.Exit(code=2) from None
    if isinstance(payload, list):
        regions, polished_md, protocol_version = payload, None, None
    elif isinstance(payload, dict):
        regions = payload.get("regions") or []
        polished_md = payload.get("polished_md")
        protocol_version = payload.get("protocol_version")
    else:
        typer.echo("submission must be a JSON list or object", err=True)
        raise typer.Exit(code=2)
    _, svc = _build_session_services(data_dir)
    verdict = asyncio.run(svc.ingest_submit_page(
        session_id, page,
        regions=regions, polished_md=polished_md, protocol_version=protocol_version,
    ))
    _echo_json(verdict)
    if not verdict.get("accepted"):
        raise typer.Exit(code=1)


@ingest_session_app.command()
def status(
    session_id: str = typer.Argument(None),
    slug: str = typer.Option(None, "--slug", help="Look up by document slug instead of session id."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Resume surface: session state plus pages done / remaining."""
    if not session_id and not slug:
        typer.echo("give a SESSION_ID or --slug <doc>", err=True)
        raise typer.Exit(code=2)
    _, svc = _build_session_services(data_dir)
    out = asyncio.run(svc.ingest_status(session_id, slug=slug))
    _exit_on_error(out)
    _echo_json(out)


@ingest_session_app.command()
def finalize(
    session_id: str = typer.Argument(...),
    allow_missing: str = typer.Option(
        None, "--allow-missing",
        help="Comma-separated pages to publish without (e.g. '3,7').",
    ),
    declared_model: str = typer.Option(
        None, "--declared-model", help="Your model id, recorded in the ingest report."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Check completeness, embed locally, and publish staging to gold atomically."""
    pages = None
    if allow_missing:
        try:
            pages = [int(p) for p in allow_missing.split(",") if p.strip()]
        except ValueError:
            typer.echo("--allow-missing wants comma-separated page numbers", err=True)
            raise typer.Exit(code=2) from None
    _, svc = _build_session_services(data_dir)
    summary = asyncio.run(svc.ingest_finalize(
        session_id, allow_missing_pages=pages, declared_model=declared_model,
    ))
    _echo_json(summary)
    if not summary.get("finalized"):
        raise typer.Exit(code=1)


@ingest_session_app.command()
def abort(
    session_id: str = typer.Argument(...),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Discard a session's staged pages. Bronze/silver stay reusable."""
    _, svc = _build_session_services(data_dir)
    out = asyncio.run(svc.ingest_abort(session_id))
    _echo_json(out)
    if not out.get("aborted"):
        raise typer.Exit(code=1)
