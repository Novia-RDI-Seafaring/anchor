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

from anchor.core.events.actor import Actor
from anchor.core.services.intent_service import (
    IntentService,
)
from anchor.infra.activity import ActivityLog
from intent_layer.timing import intent_timing

TOOL_NAMES: set[str] = {
    "list_pending_intents",
    "next_intent",
    "intents_wait",
    "resolve_intent",
    "get_intent",
    "intent_ask",
    "intent_add_item",
    "intent_update_item",
    "intent_act",
    "intent_answer",
    "intent_apply",
    "intent_decline",
    "intent_revert",
    "intent_timing",
}

_PLACE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": (
        "Where on the canvas this item belongs, in canvas coordinates. A "
        "message with a place shows as a ghost box there; a question with a "
        "place is asked beside that spot. The intent's `sketch`, when it has "
        "one, carries the positions the human drew -- use those."
    ),
    "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "width": {"type": "number"},
        "height": {"type": "number"},
    },
    "required": ["x", "y"],
    "additionalProperties": False,
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
                "far). A request drawn on the canvas also carries what the "
                "drawing said, resolved in the browser: `payload.sketch` (boxes "
                "and lines drawn as new elements; each box's `rect` is where "
                "its card goes, and its `callouts` are words drawn out of it "
                "at the spot the reader left them: build each there, side by "
                "side if they were side by side), `cuts` (a line across a "
                "table: after which row), `strikes` (an edge crossed out) and "
                "`pointers` (where each label's line starts: the card and, on "
                "a table, the row). Read `pointers` before asking what a "
                "request applies to, and offer the place the line started as "
                "the first option. Handle each one: the moment you pick one up, post a "
                "`message` saying what you are about to do, with a `place` "
                "where the result will land so a ghost box shows there while "
                "you work; work out the ops; then one intent_act call: the "
                "suggestion applied, that message marked `done`, and the "
                "question (with options) or result, resolving when nothing is "
                "left to ask. A board that shows nothing while the agent works "
                "reads as an agent doing nothing. A thread whose "
                "latest item is your own `question` with state `open` is "
                "still waiting on the human: skip it and come back later. "
                "Pass `canvas` to see one canvas's view. Omitted, it is the "
                "canvas open in the browser when exactly one is, and the "
                "result names it and counts what waits elsewhere; otherwise "
                "the whole project."
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
            "name": "intents_wait",
            "description": (
                "Wait for the next intent that needs you, and take it. Holds "
                "until one arrives (a new ask, an answer to your question, a "
                "comment in your thread) or `timeout_s` passes (default 60, at "
                "most 120), then returns {intent} or {intent: null, timed_out: "
                "true}. A thread whose latest word is yours does not wake you, "
                "and one another agent holds is skipped. The returned intent "
                "is claimed for you (`claim`, default true) so another "
                "listening agent leaves it alone. To keep listening, handle "
                "it and call again; on a timeout, just call again. `canvas` "
                "as for list_pending_intents: omitted, the canvas open in the "
                "browser when exactly one is."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "canvas": canvas_arg,
                    "timeout_s": {"type": "number", "minimum": 0, "maximum": 120},
                    "claim": {"type": "boolean"},
                },
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
            "name": "intent_timing",
            "description": (
                "How long an intent took and how many calls it cost: seconds "
                "from the ask to the first placed status (pickup), to the "
                "first suggestion, to the last agent item and to resolution; "
                "and the adapter calls made in that window, by kind and by "
                "name, from the activity log. For looking at the loop itself, "
                "not for handling the ask."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {"id": id_arg},
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
                "progress note), `question` (the ask is ambiguous: ask, offer the "
                "likely readings as `options` so the answer is one press, then "
                "wait for the human's answer via get_intent), `suggestion` (a "
                "STAGED batch of canvas ops with `text` as the rationale; the "
                "human previews it and approves or declines, and nothing "
                "changes on the canvas until approval -- the preview IS your "
                "ops, drawn on the board where they will land: a NodeAdded "
                "shows as the card with its rows at its x/y, a NodeUpdated as "
                "the card as it will read, an EdgeAdded as the line; so give "
                "every NodeAdded a real position and full data, and put the "
                "text to work on WHY rather than on describing what the ops "
                "already show). Use a staged suggestion (here, or intent_act with "
                "apply: false) only for a change that is "
                "large, destructive, or genuinely ambiguous. For the usual "
                "change -- split this table here, add the card I drew -- call "
                "intent_act instead: it lands on the canvas at once and the "
                "human gets keep / put it back, with the way back recorded. "
                "intent_apply is the human's approval verb; do not use it to "
                "approve your own staged work), "
                "`result` (a summary "
                "when you are done; then call resolve_intent). Never edit a "
                "thread's targeted elements with the canvas tools: change them "
                "through the thread. "
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
                    "place": _PLACE_SCHEMA,
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Question only: answers to offer, each one press for the "
                            "human. Offer them whenever the ask has a few likely "
                            "readings ('every other word' / 'every other row'): a "
                            "press costs less than a sentence, and the reply comes "
                            "back as the question's `answer`. Free text still answers."
                        ),
                    },
                },
                "required": ["id", "type"],
                "additionalProperties": False,
            },
        },
        {
            "name": "intent_update_item",
            "description": (
                "Change one of your own `message` items in place: its `text`, "
                "its `state`, or its `place`. Use it to narrate work in "
                "progress on the canvas. Post a placed message per element you "
                "are about to add ('1. adding LKH-5 node' at the sketch's "
                "coordinates): it shows as a ghost, `planned`. Set `state: "
                "active` on the one you are working on now, rewrite `text` as "
                "you go ('fetching page 3', 'found the measures table'), and "
                "set `state: done` once the real element has landed so the "
                "ghost can go. A message with no place has no state."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": id_arg,
                    "item_id": {"type": "string", "description": "The message item to change."},
                    "text": {"type": "string", "description": "New text."},
                    "state": {
                        "type": "string",
                        "enum": ["planned", "active", "done"],
                        "description": "Placed messages only.",
                    },
                    "place": _PLACE_SCHEMA,
                },
                "required": ["id", "item_id"],
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
            "name": "intent_act",
            "description": (
                "Act, then ask, in one call: post a `suggestion` from `text` "
                "and `ops`, apply it to the canvas at once, mark your placed "
                "status messages (`done`) done, then ask a `question` with "
                "options the human can press, or post a `result`, and "
                "`resolve` the thread if nothing is left to ask. This is the "
                "write to make once you know what to do: it replaces four "
                "calls. The human sees the change on the board with keep and "
                "put back beside it, and put back restores things exactly. "
                "If the ops cannot be applied nothing after the suggestion "
                "happens, the canvas is untouched, and the error names the "
                "failing op. Pass `apply: false` to stage the suggestion for "
                "the human to approve instead, for a change that is large or "
                "hard to undo by eye."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": id_arg,
                    "text": {"type": "string", "description": "What the change does, one or two sentences."},
                    "ops": {
                        "type": "array",
                        "items": _OP_SCHEMA,
                        "description": "Canvas ops, as for intent_add_item type=suggestion.",
                    },
                    "supersedes": {"type": "string", "description": "An earlier suggestion this replaces."},
                    "apply": {"type": "boolean", "description": "Apply at once (default true)."},
                    "done": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ids of your placed status messages to mark done.",
                    },
                    "question": {
                        "type": "object",
                        "description": "`{text, options?, place?}`: the ask that follows the act.",
                        "properties": {
                            "text": {"type": "string"},
                            "options": {"type": "array", "items": {"type": "string"}},
                            "place": _PLACE_SCHEMA,
                        },
                        "required": ["text"],
                        "additionalProperties": False,
                    },
                    "result": {"type": "string", "description": "A closing note, when there is nothing to ask."},
                    "resolve": {"type": "boolean", "description": "Resolve the thread as well (default false)."},
                },
                "required": ["id", "text", "ops"],
                "additionalProperties": False,
            },
        },
        {
            "name": "intent_apply",
            "description": (
                "Approve a pending suggestion and apply its ops to the canvas "
                "all-or-nothing, attributed to the suggestion's author with the "
                "approver recorded as the review. The human's verb for a staged "
                "suggestion; an agent acting first uses intent_act, which "
                "applies as it posts. On failure nothing is written and the "
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
            "name": "intent_revert",
            "description": (
                "Put an applied suggestion back (a human's verb). The inverse "
                "ops were recorded when it was applied, so this is atomic and "
                "exact. Use it when an agent applied its change directly and "
                "the human wants the canvas as it was."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": id_arg,
                    "item_id": {"type": "string", "description": "The applied suggestion."},
                },
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


async def call_tool(intents: IntentService, name: str, args: dict[str, Any], *,
                    actor: Actor | None = None, activity: ActivityLog | None = None) -> str:
    """Retain Anchor schemas and map its ask to the generic dispatcher.
    ``activity`` is the project's call log, for ``intent_timing``."""
    from intent_layer.adapters.mcp import call_tool as dispatch
    if name == "intent_timing":
        intent = await intents.get(args["id"])
        if intent is None:
            return json.dumps({"error": "not_found", "id": args.get("id")})
        calls = activity.read(since=intent.created_at) if activity is not None else []
        return json.dumps({"timing": intent_timing(intent, calls)})
    if name == "intent_ask":
        slug = args["workspace_slug"]
        args = {**args, "origin_canvas_id": slug, "targets": [
            {"workspace_id": slug, "node_id": node} for node in (args.get("targets") or [])
        ]}
    return await dispatch(intents, name, args, actor=actor)
