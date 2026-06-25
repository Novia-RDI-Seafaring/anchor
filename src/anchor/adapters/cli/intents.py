"""CLI commands for the agent intent queue (#148).

``anchor intents``                list pending intents (optionally one canvas).
``anchor intent resolve <id>``    mark an intent resolved with a result.
``anchor intent next``            peek the oldest pending intent.

The shell surface mirrors HTTP / MCP so an agent or a human can drive the queue
from any adapter. Reads the durable project-level intent store, so an intent
enqueued by the running server (a drop-to-ingest) is visible here even though it
was raised in another process.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR

intent_app = typer.Typer(help="Resolve and inspect agent intents.")


def _intent_service(data_dir: Path):
    from anchor.core.clock import SystemClock
    from anchor.core.services.intent_service import IntentService
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from anchor.infra.environment import config_for_data_dir
    from anchor.infra.stores.fs_intent_store import FsIntentStore

    config = config_for_data_dir(data_dir)
    return IntentService(
        FsIntentStore(config.data_dir), MemoryEventBus(), now=SystemClock().now
    )


def intents(
    canvas: str | None = typer.Option(
        None, "--canvas", "-c", help="Filter to one canvas's view."
    ),
    all_: bool = typer.Option(
        False, "--all", help="Include resolved intents, newest first."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """List pending agent intents for this project (the agent's inbox)."""
    svc = _intent_service(data_dir)
    if all_:
        items = asyncio.run(svc.list_all(canvas=canvas))
    else:
        items = asyncio.run(svc.list_pending(canvas=canvas))
    typer.echo(json.dumps({"intents": [i.to_dict() for i in items]}, indent=2))


@intent_app.command("next")
def intent_next(
    canvas: str | None = typer.Option(None, "--canvas", "-c"),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Peek the oldest pending intent (or {intent: null}). A peek, not a claim."""
    svc = _intent_service(data_dir)
    nxt = asyncio.run(svc.next(canvas=canvas))
    typer.echo(
        json.dumps({"intent": nxt.to_dict() if nxt is not None else None}, indent=2)
    )


@intent_app.command("resolve")
def intent_resolve(
    intent_id: str = typer.Argument(..., help="The intent id to resolve."),
    result: str | None = typer.Option(
        None, "--result", help="Outcome as a JSON string, or @path to a JSON file."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Mark an intent resolved, recording an optional ``--result`` payload."""
    payload: dict | None = None
    if result is not None:
        raw = (
            Path(result[1:]).read_text(encoding="utf-8")
            if result.startswith("@")
            else result
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            typer.echo(f"--result is not valid JSON: {exc}", err=True)
            raise typer.Exit(code=1) from None
    svc = _intent_service(data_dir)
    try:
        resolved = asyncio.run(svc.resolve(intent_id, payload))
    except KeyError:
        typer.echo(json.dumps({"error": "not_found", "id": intent_id}), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps({"resolved": resolved.to_dict()}, indent=2))
