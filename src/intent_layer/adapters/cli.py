"""Mountable CLI inbox; the host supplies a service instead of global state."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from intent_layer.actor import Actor, parse_actor
from intent_layer.adapters.mcp import call_tool
from intent_layer.service import IntentService


def create_cli(get_service: Callable[[], IntentService], *,
               default_actor: Actor | None = None) -> typer.Typer:
    """Return an inbox subcommand group with JSON targets and host operations."""
    app = typer.Typer(help="Inspect and reply to host intent threads.")
    actor = default_actor or Actor(kind="human", label="cli")

    @app.callback()
    def main(actor_spec: str | None = typer.Option(None, "--actor")) -> None:
        nonlocal actor
        try:
            actor = parse_actor(actor_spec) if actor_spec else default_actor or Actor(kind="human", label="cli")
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2) from None

    def parse(value: str | None, flag: str) -> Any:
        if value is None:
            return None
        raw = Path(value[1:]).read_text(encoding="utf-8") if value.startswith("@") else value
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            typer.echo(json.dumps({"error": "invalid_json", "flag": flag}), err=True)
            raise typer.Exit(1) from None

    def run(name: str, args: dict[str, Any]) -> None:
        result = asyncio.run(call_tool(get_service(), name, args, actor=actor))
        body = json.loads(result)
        typer.echo(json.dumps(body, indent=2), err="error" in body)
        if "error" in body:
            raise typer.Exit(1)

    @app.command("list")
    def list_pending(canvas: str | None = typer.Option(None, "--canvas")) -> None:
        run("list_pending_intents", {"canvas": canvas})

    @app.command("next")
    def next_intent(canvas: str | None = typer.Option(None, "--canvas")) -> None:
        run("next_intent", {"canvas": canvas})

    @app.command("show")
    def show(intent_id: str) -> None:
        run("get_intent", {"id": intent_id})

    @app.command("resolve")
    def resolve(intent_id: str, result: str | None = typer.Option(None, "--result")) -> None:
        run("resolve_intent", {"id": intent_id, "result": parse(result, "--result")})

    @app.command("ask")
    def ask(text: str = typer.Option(..., "--text"),
            origin: str | None = typer.Option(None, "--origin"),
            targets: str | None = typer.Option(None, "--targets", help="Host targets as a JSON array, or @path.")) -> None:
        run("intent_ask", {"text": text, "origin_canvas_id": origin,
                           "targets": parse(targets, "--targets")})

    @app.command("add-item")
    def add_item(intent_id: str, type_: str = typer.Option(..., "--type"),
                 text: str = typer.Option("", "--text"),
                 ops: str | None = typer.Option(None, "--ops"),
                 supersedes: str | None = typer.Option(None, "--supersedes"),
                 place: str | None = typer.Option(None, "--place"),
                 option: list[str] | None = typer.Option(None, "--option")) -> None:
        run("intent_add_item", {"id": intent_id, "type": type_, "text": text,
                                "ops": parse(ops, "--ops"), "supersedes": supersedes,
                                "place": parse(place, "--place"), "options": option})

    @app.command("update-item")
    def update_item(intent_id: str, item_id: str,
                    text: str | None = typer.Option(None, "--text"),
                    state: str | None = typer.Option(None, "--state"),
                    place: str | None = typer.Option(None, "--place")) -> None:
        run("intent_update_item", {"id": intent_id, "item_id": item_id,
                                   "text": text, "state": state, "place": parse(place, "--place")})

    @app.command("answer")
    def answer(intent_id: str, item_id: str, text: str = typer.Option(..., "--text")) -> None:
        run("intent_answer", {"id": intent_id, "item_id": item_id, "text": text})

    @app.command("apply")
    def apply(intent_id: str, item_id: str) -> None:
        run("intent_apply", {"id": intent_id, "item_id": item_id})

    @app.command("revert")
    def revert(intent_id: str, item_id: str) -> None:
        run("intent_revert", {"id": intent_id, "item_id": item_id})

    @app.command("decline")
    def decline(intent_id: str, item_id: str, comment: str | None = typer.Option(None, "--comment")) -> None:
        run("intent_decline", {"id": intent_id, "item_id": item_id, "comment": comment})

    return app
