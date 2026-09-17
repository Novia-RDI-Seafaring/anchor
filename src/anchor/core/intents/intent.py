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

from anchor.core.events.actor import Actor
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
#: - ``user_request`` — a free-text request a human typed into the web Intents
#:   panel (#323). ``payload`` carries ``{"text": <the request>}`` plus, when
#:   the author attached a canvas node as the target, the same node-ref shape
#:   ``drop_to_ingest`` uses: ``{"workspace_id": <slug>, "node_id": <id>}``.
IntentKind = Literal["drop_to_ingest", "make_reference", "attach_to_fact", "user_request"]

#: Every recognized kind, as a plain set so callers (storage, validation,
#: tests) can check membership without importing typing internals.
INTENT_KINDS: frozenset[str] = frozenset(
    {"drop_to_ingest", "make_reference", "attach_to_fact", "user_request"}
)

#: Status values an intent can carry. ``pending`` = waiting for the agent;
#: ``resolved`` = the agent handled it (success or recorded failure in
#: ``result``). Kept terminal-simple on purpose: a re-raise enqueues a new
#: intent rather than reopening an old one.
PENDING = "pending"
RESOLVED = "resolved"

#: Event type emitted on the bus when the pending set changes. Payload is just
#: ``{"count": <n>}`` — the count, never the intent payload — so a subscriber
#: learns *that* work is waiting without paying for it on every turn. The
#: same signal fires when a thread gains an item or an item changes state, so
#: a UI that refetches on it stays current (#343).
INTENT_PENDING_EVENT = "IntentPending"

# -- Scoped-ask threads (#343) ---------------------------------------------- #
#
# A thread is an intent anchored to a canvas selection (``targets``) whose
# conversation lives in ``items``: an append-only list of typed entries. A
# ``suggestion`` is a staged batch of canvas ops the human approves or
# declines; nothing on the canvas moves until approval.

ThreadItemType = Literal["message", "question", "suggestion", "result"]

THREAD_ITEM_TYPES: frozenset[str] = frozenset(
    {"message", "question", "suggestion", "result"}
)

#: ``question`` states.
QUESTION_OPEN = "open"
QUESTION_ANSWERED = "answered"

#: ``suggestion`` states. ``message`` and ``result`` carry ``state: None``.
SUGGESTION_PENDING = "pending"
SUGGESTION_APPLIED = "applied"
SUGGESTION_DECLINED = "declined"
SUGGESTION_SUPERSEDED = "superseded"

#: The canvas event vocabulary a suggestion's ops may use. Apply reuses the
#: workspace reducer, so no new mutation code exists for suggestions.
SUGGESTION_OP_TYPES: tuple[str, ...] = (
    "NodeAdded",
    "NodeUpdated",
    "NodeRemoved",
    "EdgeAdded",
    "EdgeUpdated",
    "EdgeRemoved",
)


def initial_item_state(item_type: str) -> str | None:
    """The state a freshly appended item of ``item_type`` starts in."""
    if item_type == "question":
        return QUESTION_OPEN
    if item_type == "suggestion":
        return SUGGESTION_PENDING
    return None


class ThreadItem(BaseModel):
    """One entry in a thread.

    ``author`` is the request's actor (the #322 ContextVar), stamped by the
    service; it is never client-supplied. ``ops`` / ``supersedes`` /
    ``applied_versions`` are suggestion-only; ``answer`` is question-only.
    """

    id: str = Field(default_factory=new_event_id)
    type: ThreadItemType
    author: Actor
    text: str = ""
    created_at: float = 0.0
    state: str | None = None
    answer: str | None = None
    ops: list[dict[str, Any]] | None = None
    supersedes: str | None = None
    applied_versions: list[int] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "author": self.author.model_dump(),
            "text": self.text,
            "created_at": self.created_at,
            "state": self.state,
        }
        if self.answer is not None:
            d["answer"] = self.answer
        if self.ops is not None:
            d["ops"] = [dict(op) for op in self.ops]
        if self.supersedes is not None:
            d["supersedes"] = self.supersedes
        if self.applied_versions is not None:
            d["applied_versions"] = list(self.applied_versions)
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ThreadItem:
        author_raw = raw.get("author")
        author = (
            Actor(**author_raw)
            if isinstance(author_raw, dict) and author_raw.get("kind")
            else Actor(kind="system")
        )
        ops_raw = raw.get("ops")
        versions_raw = raw.get("applied_versions")
        return cls(
            id=str(raw.get("id") or new_event_id()),
            type=raw.get("type", "message"),
            author=author,
            text=str(raw.get("text") or ""),
            created_at=float(raw.get("created_at", 0.0) or 0.0),
            state=(str(raw["state"]) if raw.get("state") is not None else None),
            answer=(str(raw["answer"]) if raw.get("answer") is not None else None),
            ops=(
                [dict(op) for op in ops_raw if isinstance(op, dict)]
                if isinstance(ops_raw, list)
                else None
            ),
            supersedes=(
                str(raw["supersedes"]) if raw.get("supersedes") is not None else None
            ),
            applied_versions=(
                [int(v) for v in versions_raw] if isinstance(versions_raw, list) else None
            ),
        )


class Intent(BaseModel):
    """One queued agent request.

    ``id`` is a stable identifier (also the on-disk filename stem). ``payload``
    is kind-specific free-form data: for ``drop_to_ingest`` it carries the
    dropped document's slug/filename and the placeholder node it should fill.
    ``result`` is set when the intent is resolved.

    Thread fields (#343, additive; records written before them load with the
    defaults): ``targets`` is the canvas selection the ask is anchored to
    (``[{workspace_id, node_id}]``), ``base_version`` the origin canvas's
    version when the ask was made, ``items`` the append-only conversation.
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
    targets: list[dict[str, Any]] = Field(default_factory=list)
    base_version: int | None = None
    items: list[ThreadItem] = Field(default_factory=list)

    def find_item(self, item_id: str) -> ThreadItem | None:
        return next((i for i in self.items if i.id == item_id), None)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "origin_canvas_id": self.origin_canvas_id,
            "target": self.target,
            "payload": dict(self.payload),
            "status": self.status,
            "created_at": self.created_at,
            "targets": [dict(t) for t in self.targets],
            "base_version": self.base_version,
            "items": [i.to_dict() for i in self.items],
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
            targets=[
                dict(t) for t in (raw.get("targets") or []) if isinstance(t, dict)
            ],
            base_version=(
                int(raw["base_version"]) if raw.get("base_version") is not None else None
            ),
            items=[
                ThreadItem.from_dict(i)
                for i in (raw.get("items") or [])
                if isinstance(i, dict)
            ],
        )
