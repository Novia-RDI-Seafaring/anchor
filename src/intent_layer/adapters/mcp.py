"""Reusable inbox dispatch with opaque host targets and operations."""
from __future__ import annotations

import json
from typing import Any

from intent_layer.actor import Actor, actor_scope
from intent_layer.models import INTENT_KINDS
from intent_layer.service import (
    IntentService,
    SuggestionApplyError,
    ThreadError,
    UnknownIntentKindError,
)

TOOL_NAMES = {
    "list_pending_intents", "next_intent", "resolve_intent", "get_intent",
    "intent_ask", "intent_add_item", "intent_update_item", "intent_answer",
    "intent_apply", "intent_revert", "intent_decline",
}


def tool_definitions(*, target_schema: dict[str, Any] | None = None,
                     op_schema: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Inbox tools. Hosts may document their opaque target/operation values."""
    from copy import deepcopy

    text = {"type": "string"}
    ident = {"id": text}
    item = {**ident, "item_id": text}
    place = {"type": "object", "properties": {
        key: {"type": "number"} for key in ("x", "y", "width", "height")
    }, "required": ["x", "y"], "additionalProperties": False}
    schemas = {
        "list_pending_intents": ({"canvas": text}, []),
        "next_intent": ({"canvas": text}, []),
        "resolve_intent": ({**ident, "result": {"type": "object"}}, ["id"]),
        "get_intent": (ident, ["id"]),
        "intent_ask": ({"origin_canvas_id": text, "text": text,
                        "targets": {"type": "array", "items": target_schema or {}}}, ["text"]),
        "intent_add_item": ({**ident, "type": {"type": "string", "enum": [
            "message", "question", "suggestion", "result"]}, "text": text,
            "ops": {"type": "array", "items": op_schema or {"type": "object"}},
            "supersedes": text, "place": place,
            "options": {"type": "array", "items": text}}, ["id", "type"]),
        "intent_update_item": ({**item, "text": text, "state": text, "place": place}, ["id", "item_id"]),
        "intent_answer": ({**item, "text": text}, ["id", "item_id", "text"]),
        "intent_apply": (item, ["id", "item_id"]),
        "intent_revert": (item, ["id", "item_id"]),
        "intent_decline": ({**item, "comment": text}, ["id", "item_id"]),
    }
    return [{"name": name, "description": f"{name}: host-independent intent inbox operation.",
             "inputSchema": {"type": "object", "properties": deepcopy(properties),
                             "required": required, "additionalProperties": False}}
            for name, (properties, required) in schemas.items()]


async def call_tool(
    intents: IntentService,
    name: str,
    args: dict[str, Any],
    *,
    actor: Actor | None = None,
) -> str:
    """Dispatch one intent tool call. Thread writes are attributed to
    ``actor`` (the connected MCP client, #322); with none given they fall
    back to the generic ``{kind: "agent", label: "mcp-agent"}``."""
    if actor is None:
        actor = Actor(kind="agent", label="mcp-agent")
    with actor_scope(actor):
        return await _dispatch(intents, name, args)


async def _dispatch(intents: IntentService, name: str, args: dict[str, Any]) -> str:
    if name == "list_pending_intents":
        pending = await intents.list_pending(canvas=args.get("canvas"))
        return json.dumps({"intents": [i.to_dict() for i in pending]})
    if name == "next_intent":
        nxt = await intents.next(canvas=args.get("canvas"))
        return json.dumps({"intent": nxt.to_dict() if nxt is not None else None})
    if name == "resolve_intent":
        try:
            resolved = await intents.resolve(args["id"], args.get("result"))
        except KeyError:
            return json.dumps({"error": "not_found", "id": args.get("id")})
        return json.dumps({"resolved": resolved.to_dict()})
    if name == "get_intent":
        intent = await intents.get(args["id"])
        if intent is None:
            return json.dumps({"error": "not_found", "id": args.get("id")})
        return json.dumps({"intent": intent.to_dict()})
    if name == "intent_ask":
        slug = args.get("origin_canvas_id")
        targets = args.get("targets")
        try:
            intent = await intents.enqueue(
                "user_request",
                origin_canvas_id=slug,
                payload={"text": args.get("text", "")},
                targets=targets,
            )
        except UnknownIntentKindError:
            return json.dumps({"error": "unknown_kind", "valid_kinds": sorted(INTENT_KINDS)})
        except ThreadError as exc:
            return json.dumps(_error(exc))
        return json.dumps({"intent": intent.to_dict()})
    try:
        if name == "intent_add_item":
            intent, item = await intents.add_item(
                args["id"],
                type=args.get("type", ""),
                text=args.get("text") or "",
                ops=args.get("ops"),
                supersedes=args.get("supersedes"),
                place=args.get("place"),
                options=args.get("options"),
            )
            return json.dumps({"intent": intent.to_dict(), "item": item.to_dict()})
        if name == "intent_update_item":
            intent, item = await intents.update_item(
                args["id"],
                args["item_id"],
                text=args.get("text"),
                state=args.get("state"),
                place=args.get("place"),
            )
            return json.dumps({"intent": intent.to_dict(), "item": item.to_dict()})
        if name == "intent_answer":
            intent, item = await intents.answer_question(
                args["id"], args["item_id"], text=args.get("text") or "",
            )
            return json.dumps({"intent": intent.to_dict(), "item": item.to_dict()})
        if name == "intent_apply":
            intent, item, applied = await intents.apply_suggestion(
                args["id"], args["item_id"],
            )
            return json.dumps(
                {"intent": intent.to_dict(), "item": item.to_dict(), "applied": applied}
            )
        if name == "intent_revert":
            intent, item, reverted = await intents.revert_suggestion(args["id"], args["item_id"])
            return json.dumps(
                {"intent": intent.to_dict(), "item": item.to_dict(), "reverted": reverted}
            )
        if name == "intent_decline":
            intent, item = await intents.decline_suggestion(
                args["id"], args["item_id"], comment=args.get("comment"),
            )
            return json.dumps({"intent": intent.to_dict(), "item": item.to_dict()})
    except KeyError:
        return json.dumps({"error": "not_found", "id": args.get("id")})
    except ThreadError as exc:
        return json.dumps(_error(exc))
    raise RuntimeError(f"unknown intent tool {name!r}")


def _error(exc: ThreadError) -> dict[str, Any]:
    if isinstance(exc, SuggestionApplyError):
        return {**exc.to_dict(), "message": str(exc)}
    return {"error": exc.code, "message": str(exc)}
