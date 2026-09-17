"""CLI commands for the agent intent queue (#148) and scoped-ask threads (#343).

``anchor intents``                     list pending intents (optionally one canvas).
``anchor intent next``                 peek the oldest pending intent.
``anchor intent resolve <id>``         mark an intent resolved with a result.
``anchor intent show <id>``            one full record incl. thread items.
``anchor intent ask <slug> --text ... --target <node>...``
                                       create a thread anchored to a selection.
``anchor intent add-item <id> --type ... [--text] [--ops] [--supersedes]``
                                       append a message / question / suggestion / result.
``anchor intent answer <id> <item> --text ...``   answer a question.
``anchor intent apply <id> <item>``               approve + apply a suggestion.
``anchor intent decline <id> <item> [--comment]`` decline a suggestion.

The shell surface mirrors HTTP / MCP so an agent or a human can drive the queue
from any adapter. Reads the durable project-level intent store, so an intent
enqueued by the running server (a drop-to-ingest) is visible here even though it
was raised in another process. Thread writes are attributed like canvas writes
(#322): ``--actor kind[:label]`` on ``anchor intent``, else ``ANCHOR_AGENT``,
else human/cli.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

from anchor.adapters.cli.common import DEFAULT_DATA_DIR
from anchor.core.events.actor import parse_actor, resolve_cli_actor, set_current_actor

intent_app = typer.Typer(help="Resolve, inspect, and reply to agent intents.")


@intent_app.callback()
def intent_main(
    actor: str | None = typer.Option(
        None,
        "--actor",
        help=(
            "Attribute thread writes to this actor as 'kind[:label]' "
            "(kind: human, agent, or system; e.g. --actor agent:claude-code). "
            "Defaults to human:cli, or agent when ANCHOR_AGENT is set."
        ),
    ),
) -> None:
    """Stamp the actor on every thread item this invocation writes (#322)."""
    if actor is not None:
        try:
            parse_actor(actor)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from None
    set_current_actor(resolve_cli_actor(actor))


def _intent_service(data_dir: Path):
    """The intent service over this project's durable store, wired to the
    canvas runtime so ``ask`` records base_version and ``apply`` can write."""
    from anchor.adapters.cli.services import _build_canvas_runtime
    from anchor.core.clock import SystemClock
    from anchor.core.services.intent_service import IntentService
    from anchor.infra.stores.fs_intent_store import FsIntentStore

    runtime = _build_canvas_runtime(data_dir)
    return IntentService(
        FsIntentStore(runtime.config.data_dir),
        runtime.bus,
        now=SystemClock().now,
        workspace=runtime.workspace,
    )


def _json_arg(value: str, flag: str) -> Any:
    """Parse ``--flag <json>`` or ``--flag @path``; exit 1 on bad JSON."""
    raw = Path(value[1:]).read_text(encoding="utf-8") if value.startswith("@") else value
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"{flag} is not valid JSON: {exc}", err=True)
        raise typer.Exit(code=1) from None


def _run(coro):
    """Run a thread command body, turning domain errors into the one-line
    stderr JSON + exit 1 the other intent commands print."""
    from anchor.core.services.intent_service import SuggestionApplyError, ThreadError

    try:
        return asyncio.run(coro)
    except KeyError as exc:
        typer.echo(json.dumps({"error": "not_found", "id": exc.args[0]}), err=True)
        raise typer.Exit(code=1) from None
    except SuggestionApplyError as exc:
        typer.echo(json.dumps({**exc.to_dict(), "message": str(exc)}), err=True)
        raise typer.Exit(code=1) from None
    except ThreadError as exc:
        typer.echo(json.dumps({"error": exc.code, "message": str(exc)}), err=True)
        raise typer.Exit(code=1) from None


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
        payload = _json_arg(result, "--result")
    svc = _intent_service(data_dir)
    try:
        resolved = asyncio.run(svc.resolve(intent_id, payload))
    except KeyError:
        typer.echo(json.dumps({"error": "not_found", "id": intent_id}), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps({"resolved": resolved.to_dict()}, indent=2))


@intent_app.command("show")
def intent_show(
    intent_id: str = typer.Argument(..., help="The intent id."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Print one intent in full: targets, base_version, and every thread item."""
    svc = _intent_service(data_dir)
    intent = asyncio.run(svc.get(intent_id))
    if intent is None:
        typer.echo(json.dumps({"error": "not_found", "id": intent_id}), err=True)
        raise typer.Exit(code=1)
    typer.echo(json.dumps({"intent": intent.to_dict()}, indent=2))


@intent_app.command("ask")
def intent_ask(
    slug: str = typer.Argument(..., help="The canvas the ask is anchored to."),
    text: str = typer.Option(..., "--text", help="The ask."),
    target: list[str] = typer.Option(
        [], "--target", help="Node id on the canvas the ask is about (repeatable)."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Create a thread: a user_request anchored to a canvas selection."""
    svc = _intent_service(data_dir)
    intent = _run(
        svc.enqueue(
            "user_request",
            origin_canvas_id=slug,
            payload={"text": text},
            targets=[{"workspace_id": slug, "node_id": n} for n in target],
        )
    )
    typer.echo(json.dumps({"intent": intent.to_dict()}, indent=2))


@intent_app.command("add-item")
def intent_add_item(
    intent_id: str = typer.Argument(..., help="The intent (thread) id."),
    type_: str = typer.Option(
        ..., "--type", help="message | question | suggestion | result."
    ),
    text: str = typer.Option("", "--text", help="Comment, question, rationale, or summary."),
    ops: str | None = typer.Option(
        None, "--ops", help="Suggestion only: ops as a JSON array, or @path to a JSON file."
    ),
    supersedes: str | None = typer.Option(
        None, "--supersedes", help="Suggestion only: the earlier suggestion this revises."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Append an item to a thread (author = this invocation's actor)."""
    parsed_ops = _json_arg(ops, "--ops") if ops is not None else None
    svc = _intent_service(data_dir)
    intent, item = _run(
        svc.add_item(intent_id, type=type_, text=text, ops=parsed_ops, supersedes=supersedes)
    )
    typer.echo(json.dumps({"intent": intent.to_dict(), "item": item.to_dict()}, indent=2))


@intent_app.command("answer")
def intent_answer(
    intent_id: str = typer.Argument(..., help="The intent (thread) id."),
    item_id: str = typer.Argument(..., help="The question item id."),
    text: str = typer.Option(..., "--text", help="The answer."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Answer an open question in a thread."""
    svc = _intent_service(data_dir)
    intent, item = _run(svc.answer_question(intent_id, item_id, text=text))
    typer.echo(json.dumps({"intent": intent.to_dict(), "item": item.to_dict()}, indent=2))


@intent_app.command("apply")
def intent_apply(
    intent_id: str = typer.Argument(..., help="The intent (thread) id."),
    item_id: str = typer.Argument(..., help="The suggestion item id."),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Approve a pending suggestion and apply its ops all-or-nothing."""
    svc = _intent_service(data_dir)
    intent, item, applied = _run(svc.apply_suggestion(intent_id, item_id))
    typer.echo(
        json.dumps(
            {"intent": intent.to_dict(), "item": item.to_dict(), "applied": applied},
            indent=2,
        )
    )


@intent_app.command("decline")
def intent_decline(
    intent_id: str = typer.Argument(..., help="The intent (thread) id."),
    item_id: str = typer.Argument(..., help="The suggestion item id."),
    comment: str | None = typer.Option(
        None, "--comment", help="Feedback, recorded as a message item."
    ),
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, "--data-dir", "-d"),
) -> None:
    """Decline a pending suggestion, optionally with a comment."""
    svc = _intent_service(data_dir)
    intent, item = _run(svc.decline_suggestion(intent_id, item_id, comment=comment))
    typer.echo(json.dumps({"intent": intent.to_dict(), "item": item.to_dict()}, indent=2))
