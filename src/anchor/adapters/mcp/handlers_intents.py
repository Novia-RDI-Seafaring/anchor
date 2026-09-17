"""MCP tool handlers for the agent intent queue (#148) and scoped-ask
threads (#343).

These are the agent-facing pull half of the push-notify / pull-payload design:
a harness fetches pending intents, peeks the next one, and reports a result back
when it has handled one. The push half is the ``IntentPending`` count signal on
the HTTP SSE stream; an agent that cannot subscribe just calls these on its own
cadence.

Threads add the reply channel: ``intent_add_item`` posts a message, question,
staged suggestion, or result into a thread. ``intent_answer`` /
``intent_apply`` / ``intent_decline`` are the human's verbs (answer a
question, approve or decline a suggestion); they exist here for adapter
parity, and the skill text tells agents not to call them on their own asks.

The inbox tools and ``intent_add_item`` live in the always-advertised CORE
set; the human-side verbs sit in the gated ``intent_threads`` capability
(see ``anchor.adapters.mcp.tiering``). Every write is attributed to the
connected client's actor (#322) so item ``author`` is never client-supplied.
"""
from __future__ import annotations

import json
from typing import Any

from anchor.core.events.actor import Actor, actor_scope
from anchor.core.intents.intent import INTENT_KINDS
from anchor.core.services.intent_service import (
    IntentService,
    SuggestionApplyError,
    ThreadError,
    UnknownIntentKindError,
)

TOOL_NAMES: set[str] = {
    "list_pending_intents",
    "next_intent",
    "resolve_intent",
    "get_intent",
    "intent_ask",
    "intent_add_item",
    "intent_answer",
    "intent_apply",
    "intent_decline",
}

_OP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "NodeAdded", "NodeUpdated", "NodeRemoved",
                "EdgeAdded", "EdgeUpdated", "EdgeRemoved",
            ],
        },
        "payload": {
            "type": "object",
            "description": (
                "The canvas event payload: NodeAdded {id?, node_type, label, x, y, "
                "data}; NodeUpdated {id, fields}; NodeRemoved {id}; EdgeAdded "
                "{id?, source, target, edge_type?, data?}; EdgeUpdated {id, "
                "fields}; EdgeRemoved {id}. A NodeAdded/EdgeAdded `id` is a "
                "client id later ops in the same batch may reference; apply "
                "maps it to the real id."
            ),
        },
    },
    "required": ["type", "payload"],
    "additionalProperties": False,
}


def tool_definitions() -> list[dict[str, Any]]:
    canvas_arg = {
        "type": "string",
        "description": (
            "Optional canvas slug to filter to. Omit for the whole project. "
            "An intent raised on one canvas is visible from the canvas it "
            "targets too."
        ),
    }
    id_arg = {"type": "string", "description": "The intent (thread) id."}
    item_arg = {"type": "string", "description": "The thread item id."}
    return [
        {
            "name": "list_pending_intents",
            "description": (
                "List the pending agent intents for this project: user canvas "
                "actions waiting for the agent to act on (e.g. a document "
                "dropped onto the canvas in a harness-ingest project, or a "
                "free-text user_request typed into the web Intents panel or "
                "asked about a canvas selection). This is your inbox: drain it "
                "at the start of any Anchor task and whenever you are idle. "
                "Each record carries `targets` ([{workspace_id, node_id}], the "
                "canvas selection the ask is anchored to), `base_version` (the "
                "canvas version when it was asked) and `items` (the thread so "
                "far). Handle each one, reply in its thread with "
                "intent_add_item, then call resolve_intent. A thread whose "
                "latest item is your own `question` with state `open` is "
                "still waiting on the human: skip it and come back later. "
                "Pass `canvas` to see one canvas's view; omit it for the "
                "project."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"canvas": canvas_arg},
                "additionalProperties": False,
            },
        },
        {
            "name": "next_intent",
            "description": (
                "Peek the single oldest pending intent for this project (or for "
                "`canvas`), or {intent: null} when the queue is empty. A peek, "
                "not a claim. The record includes `targets` and `items`: read "
                "the targeted elements with canvas_get_state, reply in the "
                "thread with intent_add_item, then resolve_intent(id, result)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"canvas": canvas_arg},
                "additionalProperties": False,
            },
        },
        {
            "name": "resolve_intent",
            "description": (
                "Mark a pending intent resolved once you have handled it (e.g. "
                "finished the harness ingest of a dropped document, or posted "
                "the `result` item of a thread). `result` is free-form JSON "
                "recording the outcome (the produced slug, a status, an error). "
                "Idempotent."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The intent id to resolve."},
                    "result": {
                        "type": "object",
                        "description": "Outcome payload recorded on the intent.",
                    },
                },
                "required": ["id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_intent",
            "description": (
                "Read one intent (thread) in full: targets, base_version, and "
                "every item with its state (a question's answer, a "
                "suggestion's pending/applied/declined/superseded state). Use "
                "it to check whether the human answered your question or "
                "approved a suggestion before continuing."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"id": id_arg},
                "required": ["id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "intent_ask",
            "description": (
                "Create a thread: a user_request anchored to a canvas "
                "selection. `workspace_slug` is the canvas, `text` the ask, "
                "`targets` the node ids it is about. The server records the "
                "canvas version as base_version. Humans normally do this from "
                "the canvas; use it when relaying an ask on someone's behalf."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "workspace_slug": {"type": "string"},
                    "text": {"type": "string", "description": "The ask."},
                    "targets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Node ids on `workspace_slug` the ask is about.",
                    },
                },
                "required": ["workspace_slug", "text"],
                "additionalProperties": False,
            },
        },
        {
            "name": "intent_add_item",
            "description": (
                "Reply in a thread. `type` is one of: `message` (a comment or "
                "progress note), `question` (the ask is ambiguous: ask, then "
                "wait for the human's answer via get_intent), `suggestion` (a "
                "STAGED batch of canvas ops with `text` as the rationale; the "
                "human previews it and approves or declines, and nothing "
                "changes on the canvas until approval), `result` (a summary "
                "when you are done; then call resolve_intent). Never edit a "
                "thread's targeted elements directly: propose a suggestion. "
                "Group ops that depend on each other into one suggestion; keep "
                "independent changes as separate suggestions so partial "
                "approval is safe. A revision after feedback is a new "
                "suggestion with `supersedes` naming the earlier one. Ops use "
                "the canvas event vocabulary; a NodeAdded/EdgeAdded may carry "
                "a client `id` that later ops in the same batch reference."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": id_arg,
                    "type": {
                        "type": "string",
                        "enum": ["message", "question", "suggestion", "result"],
                    },
                    "text": {
                        "type": "string",
                        "description": "Comment, question, rationale, or summary.",
                    },
                    "ops": {
                        "type": "array",
                        "items": _OP_SCHEMA,
                        "description": "Suggestion only: the staged canvas ops.",
                    },
                    "supersedes": {
                        "type": "string",
                        "description": "Suggestion only: the earlier suggestion this revises.",
                    },
                },
                "required": ["id", "type"],
                "additionalProperties": False,
            },
        },
        {
            "name": "intent_answer",
            "description": (
                "Answer an open question in a thread (a human's verb; agents "
                "wait for the human instead of answering their own questions)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": id_arg,
                    "item_id": item_arg,
                    "text": {"type": "string", "description": "The answer."},
                },
                "required": ["id", "item_id", "text"],
                "additionalProperties": False,
            },
        },
        {
            "name": "intent_apply",
            "description": (
                "Approve a pending suggestion and apply its ops to the canvas "
                "all-or-nothing, attributed to the suggestion's author with the "
                "approver recorded as the review. A human's verb: do not apply "
                "your own suggestions. On failure nothing is written and the "
                "result names the failing op index and reason (`stale` when "
                "an element no longer exists)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"id": id_arg, "item_id": item_arg},
                "required": ["id", "item_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "intent_decline",
            "description": (
                "Decline a pending suggestion, optionally with a `comment` that "
                "is recorded as a message item (feedback the agent can revise "
                "against). A human's verb."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": id_arg,
                    "item_id": item_arg,
                    "comment": {"type": "string"},
                },
                "required": ["id", "item_id"],
                "additionalProperties": False,
            },
        },
    ]


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
        slug = args["workspace_slug"]
        targets = [
            {"workspace_id": slug, "node_id": node}
            for node in (args.get("targets") or [])
        ]
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
