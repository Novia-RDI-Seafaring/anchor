"""MCP tool handlers for the agent intent queue (#148).

These are the agent-facing pull half of the push-notify / pull-payload design:
a harness fetches pending intents, peeks the next one, and reports a result back
when it has handled one. The push half is the ``IntentPending`` count signal on
the HTTP SSE stream; an agent that cannot subscribe just calls these on its own
cadence.

The intent queue is a primary agent workflow, so these tools live in the
always-advertised CORE set (see ``anchor.adapters.mcp.tiering``).
"""
from __future__ import annotations

import json
from typing import Any

from anchor.core.services.intent_service import IntentService

TOOL_NAMES: set[str] = {
    "list_pending_intents",
    "next_intent",
    "resolve_intent",
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
    return [
        {
            "name": "list_pending_intents",
            "description": (
                "List the pending agent intents for this project: user canvas "
                "actions waiting for the agent to act on (e.g. a document "
                "dropped onto the canvas in a harness-ingest project). This is "
                "your inbox. Pull it when the IntentPending signal fires or on "
                "your own cadence, handle each one, then call resolve_intent. "
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
                "not a claim: handle it, then call resolve_intent(id, result)."
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
                "finished the harness ingest of a dropped document). `result` is "
                "free-form JSON recording the outcome (the produced slug, a "
                "status, an error). Idempotent."
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
    ]


async def call_tool(intents: IntentService, name: str, args: dict[str, Any]) -> str:
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
    raise RuntimeError(f"unknown intent tool {name!r}")
