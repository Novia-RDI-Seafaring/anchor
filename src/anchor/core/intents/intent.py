"""Intent model + kinds — the agent's request queue (issue #148).

An :class:`Intent` is a durable "the user wants the agent to do X" record. It is
the queue half of the push-notify / pull-payload design: a lightweight
``IntentPending`` signal on the event bus tells a harness *something* is waiting,
and the harness pulls the full payload from this store on its own cadence.

Scope is the PROJECT, not a single canvas. Each intent carries
``origin_canvas_id`` (where the action was raised) and an optional ``target``
(where the result should land, when different). A per-canvas view is just a
filter over the project store, so an intent raised on canvas A is visible from
canvas B in the same project.

Pure model: no I/O, no framework imports. The durable store (``infra``) and the
adapters (HTTP / MCP / CLI) wrap it.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from anchor.core.ids import new_event_id

#: The kinds of request the queue understands.
#:
#: - ``drop_to_ingest`` — a user dropped a document onto the canvas and the
#:   project's ingestion is harness-driven, so the *agent* must run the ingest
#:   (``ingest_begin -> submit_page -> finalize``). This is the kind wired
#:   end-to-end in #148.
#: - ``make_reference`` / ``attach_to_fact`` — references-store requests
#:   (#147). The queue SUPPORTS them (they are valid kinds and persist like any
#:   other intent), but their authoring UX is built separately under #147; the
#:   queue does not enqueue them yet.
IntentKind = Literal["drop_to_ingest", "make_reference", "attach_to_fact"]

#: Every recognized kind, as a plain set so callers (storage, validation,
#: tests) can check membership without importing typing internals.
INTENT_KINDS: frozenset[str] = frozenset(
    {"drop_to_ingest", "make_reference", "attach_to_fact"}
)

#: Status values an intent can carry. ``pending`` = waiting for the agent;
#: ``resolved`` = the agent handled it (success or recorded failure in
#: ``result``). Kept terminal-simple on purpose: a re-raise enqueues a new
#: intent rather than reopening an old one.
PENDING = "pending"
RESOLVED = "resolved"

#: Event type emitted on the bus when the pending set changes. Payload is just
#: ``{"count": <n>}`` — the count, never the intent payload — so a subscriber
#: learns *that* work is waiting without paying for it on every turn.
INTENT_PENDING_EVENT = "IntentPending"


class Intent(BaseModel):
    """One queued agent request.

    ``id`` is a stable identifier (also the on-disk filename stem). ``payload``
    is kind-specific free-form data: for ``drop_to_ingest`` it carries the
    dropped document's slug/filename and the placeholder node it should fill.
    ``result`` is set when the intent is resolved.
    """

    id: str = Field(default_factory=new_event_id)
    kind: IntentKind
    origin_canvas_id: str | None = None
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = PENDING
    created_at: float = 0.0
    resolved_at: float | None = None
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "origin_canvas_id": self.origin_canvas_id,
            "target": self.target,
            "payload": dict(self.payload),
            "status": self.status,
            "created_at": self.created_at,
        }
        if self.resolved_at is not None:
            d["resolved_at"] = self.resolved_at
        if self.result is not None:
            d["result"] = self.result
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Intent:
        return cls(
            id=str(raw.get("id") or new_event_id()),
            kind=raw.get("kind", "drop_to_ingest"),
            origin_canvas_id=(
                str(raw["origin_canvas_id"])
                if raw.get("origin_canvas_id") is not None
                else None
            ),
            target=(str(raw["target"]) if raw.get("target") is not None else None),
            payload=dict(raw.get("payload") or {}),
            status=str(raw.get("status", PENDING) or PENDING),
            created_at=float(raw.get("created_at", 0.0) or 0.0),
            resolved_at=(
                float(raw["resolved_at"]) if raw.get("resolved_at") is not None else None
            ),
            result=(dict(raw["result"]) if isinstance(raw.get("result"), dict) else None),
        )
