"""IntentService — enqueue / list / resolve agent intents (#148) and the
thread operations of scoped asks (#343).

This is the eventing layer over the durable project-level intent store. It owns
the two halves of the push-notify / pull-payload transport:

- **pull**: ``list_pending`` / ``next`` / ``resolve`` read and mutate the
  durable store, so a harness fetches the full payload on its own cadence.
- **push (signal only)**: after any change to the pending set — or to a
  thread — it publishes a lightweight ``IntentPending {count}`` event on the
  bus. Subscribers learn *that* something changed without paying for the
  payload on every turn.

Threads (#343): an intent may carry ``targets`` (the canvas selection it is
anchored to), ``base_version`` (the origin canvas's version at ask time) and
``items`` (an append-only conversation of ``message`` / ``question`` /
``suggestion`` / ``result`` entries). A ``suggestion`` is a staged batch of
canvas ops; :meth:`apply_suggestion` hands it to
``WorkspaceService.apply_batch`` which applies it all-or-nothing under the
workspace lock. Item ``author`` is always the ambient actor (#322).

Pure core: it depends on the store port, the event-bus port, a clock, and
(optionally) the workspace service, never on a concrete adapter. The
``workspace_id`` carried on the bus event is set to the originating canvas (or
a project-level sentinel) so a per-canvas SSE subscriber sees the signal.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from anchor.core.events.actor import SYSTEM_ACTOR, Actor, current_actor
from anchor.core.events.envelope import DomainEvent
from anchor.core.intents.intent import (
    INTENT_KINDS,
    INTENT_PENDING_EVENT,
    PENDING,
    QUESTION_ANSWERED,
    RESOLVED,
    SUGGESTION_APPLIED,
    SUGGESTION_DECLINED,
    SUGGESTION_OP_TYPES,
    SUGGESTION_PENDING,
    SUGGESTION_SUPERSEDED,
    THREAD_ITEM_TYPES,
    Intent,
    IntentKind,
    ThreadItem,
    initial_item_state,
)
from anchor.core.ports.event_bus import EventBus
from anchor.core.ports.intent_store import IntentStore
from anchor.core.services.workspace_batch import BatchApplyError
from anchor.core.services.workspace_service import WorkspaceService

#: Bus ``workspace_id`` used for the count signal when an intent has no
#: originating canvas. A project-level subscriber (or the global firehose)
#: still receives it; a per-canvas SSE stream filters on the canvas id.
PROJECT_SIGNAL_ID = "_project"


class UnknownIntentKindError(ValueError):
    """Raised when an enqueue uses a kind the queue does not recognize."""


class ThreadError(ValueError):
    """A thread operation was rejected. ``code`` is a stable machine-readable
    reason adapters surface verbatim (``invalid_targets``, ``invalid_item``,
    ``invalid_ops``, ``item_not_found``, ``not_a_question``,
    ``not_a_suggestion``, ``not_pending``, ``no_canvas``,
    ``workspace_unavailable``)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        # Adapters return this attribute, never str(exc): the text is a
        # literal authored here, and keeping it separate from the exception's
        # own rendering is what lets the analyzer see that no exception text
        # (or stack trace) flows to a client.
        self.message = message


class SuggestionApplyError(ThreadError):
    """A suggestion's ops failed validation; nothing was applied. Carries the
    failing op index, the reason, and whether the op was stale."""

    def __init__(self, cause: BatchApplyError) -> None:
        super().__init__("apply_failed", "suggestion could not be applied; nothing was changed")
        self.failing_index = cause.failing_index
        self.reason = cause.reason
        self.stale = cause.stale

    def to_dict(self) -> dict[str, Any]:
        # `failing_op_index` duplicates `failing_index` so both the spec's
        # name and the web client's read the same value.
        return {
            "error": self.code,
            "failing_index": self.failing_index,
            "failing_op_index": self.failing_index,
            "reason": self.reason,
            "stale": self.stale,
        }


def _validate_targets(targets: Any) -> list[dict[str, Any]]:
    if targets is None:
        return []
    if not isinstance(targets, list):
        raise ThreadError("invalid_targets", "targets must be a list of {workspace_id, node_id}")
    out: list[dict[str, Any]] = []
    for t in targets:
        if not isinstance(t, dict):
            raise ThreadError("invalid_targets", "each target must be {workspace_id, node_id}")
        ws = t.get("workspace_id")
        node = t.get("node_id")
        if not isinstance(ws, str) or not ws or not isinstance(node, str) or not node:
            raise ThreadError(
                "invalid_targets", "each target needs string workspace_id and node_id",
            )
        out.append({"workspace_id": ws, "node_id": node})
    return out


def _validate_ops(ops: Any) -> list[dict[str, Any]]:
    """Shape-check a suggestion's ops at post time. Canvas-level validity
    (does the node exist, is the payload complete) is checked at apply
    time against the live state, so a suggestion can be staged against a
    canvas that keeps moving."""
    if not isinstance(ops, list) or not ops:
        raise ThreadError("invalid_ops", "a suggestion needs a non-empty ops list")
    out: list[dict[str, Any]] = []
    for index, op in enumerate(ops):
        if not isinstance(op, dict):
            raise ThreadError("invalid_ops", f"op {index} must be an object {{type, payload}}")
        op_type = op.get("type")
        if op_type not in SUGGESTION_OP_TYPES:
            raise ThreadError(
                "invalid_ops",
                f"op {index}: unknown type {op_type!r}; expected one of "
                f"{', '.join(SUGGESTION_OP_TYPES)}",
            )
        payload = op.get("payload")
        if not isinstance(payload, dict):
            raise ThreadError("invalid_ops", f"op {index}: payload must be an object")
        out.append({"type": op_type, "payload": dict(payload)})
    return out


class IntentService:
    def __init__(
        self,
        store: IntentStore,
        bus: EventBus,
        *,
        now: Callable[[], float] | None = None,
        workspace: WorkspaceService | None = None,
    ) -> None:
        self._store = store
        self._bus = bus
        self._now = now
        self._workspace = workspace

    def _ts(self) -> float:
        return self._now() if callable(self._now) else 0.0

    @staticmethod
    def _actor() -> Actor:
        """The ambient actor (#322); ``system`` when no adapter scoped one."""
        return current_actor() or SYSTEM_ACTOR

    async def enqueue(
        self,
        kind: IntentKind | str,
        *,
        origin_canvas_id: str | None = None,
        target: str | None = None,
        payload: dict[str, Any] | None = None,
        targets: list[dict[str, Any]] | None = None,
    ) -> Intent:
        """Add a pending intent and fire the ``IntentPending`` count signal.

        ``targets`` (#343) anchors the intent to a canvas selection and makes
        it a thread. When the origin canvas exists, its current version is
        recorded as ``base_version`` server-side (never client-supplied).

        Raises :class:`UnknownIntentKindError` for an unrecognized kind so a
        caller never silently enqueues something no handler understands, and
        :class:`ThreadError` (``invalid_targets``) for a malformed selection.
        """
        if kind not in INTENT_KINDS:
            raise UnknownIntentKindError(
                f"unknown intent kind {kind!r}; expected one of {sorted(INTENT_KINDS)}"
            )
        clean_targets = _validate_targets(targets)
        base_version: int | None = None
        if origin_canvas_id is not None and self._workspace is not None:
            base_version = await self._workspace.version_of(origin_canvas_id)
        intent = Intent(
            kind=kind,  # type: ignore[arg-type]
            origin_canvas_id=origin_canvas_id,
            target=target,
            payload=dict(payload or {}),
            status=PENDING,
            created_at=self._ts(),
            targets=clean_targets,
            base_version=base_version,
        )
        stored = await self._store.add(intent)
        await self._signal_pending(origin_canvas_id)
        return stored

    async def list_pending(self, *, canvas: str | None = None) -> list[Intent]:
        """Pending intents for this project, oldest first.

        ``canvas`` filters to a per-canvas view (matching ``origin_canvas_id``
        or ``target``); omit it for the whole project. A cross-canvas intent is
        therefore visible from the canvas that raised it and from the canvas it
        targets.
        """
        items = [i for i in await self._store.list() if i.status == PENDING]
        if canvas is not None:
            items = [
                i
                for i in items
                if i.origin_canvas_id == canvas or i.target == canvas
            ]
        items.sort(key=lambda i: (i.created_at, i.id))
        return items

    async def list_all(self, *, canvas: str | None = None) -> list[Intent]:
        """Every intent (pending + resolved), newest first. For audit/UI."""
        items = await self._store.list()
        if canvas is not None:
            items = [
                i
                for i in items
                if i.origin_canvas_id == canvas or i.target == canvas
            ]
        items.sort(key=lambda i: (i.created_at, i.id), reverse=True)
        return items

    async def next(self, *, canvas: str | None = None) -> Intent | None:
        """The oldest pending intent (optionally for one canvas), or ``None``.

        A peek, not a claim: it does not mark the intent in-flight. The handler
        calls :meth:`resolve` when done, which is the only state transition.
        """
        pending = await self.list_pending(canvas=canvas)
        return pending[0] if pending else None

    async def get(self, intent_id: str) -> Intent | None:
        return await self._store.get(intent_id)

    async def resolve(
        self, intent_id: str, result: dict[str, Any] | None = None
    ) -> Intent:
        """Mark an intent resolved and re-fire the count signal.

        Returns the updated intent. Raises ``KeyError`` for an unknown id.
        Re-resolving an already-resolved intent is a no-op beyond refreshing
        ``result`` (kept idempotent so a retrying agent is safe).

        Resolving never touches thread items (#343): the agent's flow is
        "post a result, then resolve" while the human approves or declines
        suggestions on their own time, so pending suggestions stay pending
        and :meth:`apply_suggestion` / :meth:`decline_suggestion` keep
        working on a resolved thread.
        """
        intent = await self._store.get(intent_id)
        if intent is None:
            raise KeyError(intent_id)
        intent.status = RESOLVED
        intent.resolved_at = self._ts()
        if result is not None:
            intent.result = dict(result)
        await self._store.replace(intent)
        await self._signal_pending(intent.origin_canvas_id)
        return intent

    # -- threads (#343) ---------------------------------------------------- #

    async def _require(self, intent_id: str) -> Intent:
        intent = await self._store.get(intent_id)
        if intent is None:
            raise KeyError(intent_id)
        return intent

    async def add_item(
        self,
        intent_id: str,
        *,
        type: str,
        text: str = "",
        ops: list[dict[str, Any]] | None = None,
        supersedes: str | None = None,
    ) -> tuple[Intent, ThreadItem]:
        """Append an item to a thread. ``author`` is the ambient actor.

        ``message`` / ``result`` need ``text``; ``question`` starts ``open``;
        ``suggestion`` needs a non-empty ``ops`` list and starts ``pending``.
        ``supersedes`` names an earlier suggestion in the same thread; if that
        one is still pending it becomes ``superseded``. Raises ``KeyError``
        for an unknown intent and :class:`ThreadError` for a bad item.
        """
        if type not in THREAD_ITEM_TYPES:
            raise ThreadError(
                "invalid_item",
                f"unknown item type {type!r}; expected one of {sorted(THREAD_ITEM_TYPES)}",
            )
        text = text if isinstance(text, str) else ""
        if type in ("message", "question") and not text.strip():
            raise ThreadError("invalid_item", f"a {type} needs text")
        clean_ops: list[dict[str, Any]] | None = None
        if type == "suggestion":
            clean_ops = _validate_ops(ops)
        elif ops:
            raise ThreadError("invalid_item", "only a suggestion carries ops")
        if supersedes is not None and type != "suggestion":
            raise ThreadError("invalid_item", "only a suggestion can supersede another")
        intent = await self._require(intent_id)
        if supersedes is not None:
            prior = intent.find_item(supersedes)
            if prior is None or prior.type != "suggestion":
                raise ThreadError(
                    "item_not_found", f"supersedes {supersedes!r} is not a suggestion here",
                )
            if prior.state == SUGGESTION_PENDING:
                prior.state = SUGGESTION_SUPERSEDED
        item = ThreadItem(
            type=type,  # type: ignore[arg-type]
            author=self._actor(),
            text=text,
            created_at=self._ts(),
            state=initial_item_state(type),
            ops=clean_ops,
            supersedes=supersedes,
        )
        intent.items.append(item)
        await self._store.replace(intent)
        await self._signal_pending(intent.origin_canvas_id)
        return intent, item

    async def answer_question(
        self, intent_id: str, item_id: str, *, text: str,
    ) -> tuple[Intent, ThreadItem]:
        """Answer an open question. Re-answering replaces the answer."""
        if not isinstance(text, str) or not text.strip():
            raise ThreadError("invalid_item", "an answer needs text")
        intent = await self._require(intent_id)
        item = self._require_item(intent, item_id)
        if item.type != "question":
            raise ThreadError("not_a_question", f"item {item_id!r} is a {item.type}")
        item.answer = text
        item.state = QUESTION_ANSWERED
        await self._store.replace(intent)
        await self._signal_pending(intent.origin_canvas_id)
        return intent, item

    async def apply_suggestion(
        self, intent_id: str, item_id: str,
    ) -> tuple[Intent, ThreadItem, dict[str, Any]]:
        """Approve a pending suggestion: apply its ops all-or-nothing.

        The canvas is the thread's ``origin_canvas_id`` (or the first
        target's ``workspace_id``). Actor = the suggestion's author,
        ``causation_id`` = the item id, approver = the ambient actor. On
        success the item becomes ``applied`` with ``applied_versions``; the
        third return value is ``{versions, id_map, events}``. On failure a
        :class:`SuggestionApplyError` names the failing op and nothing is
        written; the item stays ``pending`` (the UI shows it as stale).
        """
        if self._workspace is None:
            raise ThreadError(
                "workspace_unavailable", "no workspace service is wired for apply",
            )
        intent = await self._require(intent_id)
        item = self._require_item(intent, item_id)
        if item.type != "suggestion":
            raise ThreadError("not_a_suggestion", f"item {item_id!r} is a {item.type}")
        if item.state != SUGGESTION_PENDING:
            raise ThreadError("not_pending", f"suggestion {item_id!r} is {item.state}")
        slug = self._thread_canvas(intent)
        try:
            _state, envelopes, id_map = await self._workspace.apply_batch(
                slug,
                list(item.ops or []),
                actor=item.author,
                causation_id=item.id,
                approver=self._actor(),
            )
        except BatchApplyError as exc:
            raise SuggestionApplyError(exc) from exc
        item.state = SUGGESTION_APPLIED
        item.applied_versions = [env.version for env in envelopes]
        await self._store.replace(intent)
        await self._signal_pending(intent.origin_canvas_id)
        return intent, item, {
            "workspace_id": slug,
            "versions": list(item.applied_versions),
            "id_map": dict(id_map),
            "events": [env.model_dump() for env in envelopes],
        }

    async def decline_suggestion(
        self, intent_id: str, item_id: str, *, comment: str | None = None,
    ) -> tuple[Intent, ThreadItem]:
        """Decline a pending suggestion; an optional ``comment`` is recorded
        as a ``message`` item by the ambient actor so it reads as feedback."""
        intent = await self._require(intent_id)
        item = self._require_item(intent, item_id)
        if item.type != "suggestion":
            raise ThreadError("not_a_suggestion", f"item {item_id!r} is a {item.type}")
        if item.state != SUGGESTION_PENDING:
            raise ThreadError("not_pending", f"suggestion {item_id!r} is {item.state}")
        item.state = SUGGESTION_DECLINED
        if isinstance(comment, str) and comment.strip():
            intent.items.append(
                ThreadItem(
                    type="message",
                    author=self._actor(),
                    text=comment,
                    created_at=self._ts(),
                    state=None,
                )
            )
        await self._store.replace(intent)
        await self._signal_pending(intent.origin_canvas_id)
        return intent, item

    @staticmethod
    def _require_item(intent: Intent, item_id: str) -> ThreadItem:
        item = intent.find_item(item_id)
        if item is None:
            raise ThreadError("item_not_found", f"no item {item_id!r} on intent {intent.id!r}")
        return item

    @staticmethod
    def _thread_canvas(intent: Intent) -> str:
        if intent.origin_canvas_id:
            return intent.origin_canvas_id
        for t in intent.targets:
            ws = t.get("workspace_id")
            if isinstance(ws, str) and ws:
                return ws
        raise ThreadError("no_canvas", f"intent {intent.id!r} names no canvas to apply to")

    async def pending_count(self) -> int:
        return len(await self.list_pending())

    async def _signal_pending(self, origin_canvas_id: str | None) -> None:
        """Publish ``IntentPending {count}`` — count only, never the payload."""
        count = await self.pending_count()
        await self._bus.publish(
            DomainEvent(
                workspace_id=origin_canvas_id or PROJECT_SIGNAL_ID,
                type=INTENT_PENDING_EVENT,
                ts=self._ts(),
                payload={"count": count},
            )
        )


__all__ = [
    "PROJECT_SIGNAL_ID",
    "IntentService",
    "SuggestionApplyError",
    "ThreadError",
    "UnknownIntentKindError",
]
