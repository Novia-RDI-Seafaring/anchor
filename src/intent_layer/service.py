"""IntentService - enqueue / list / resolve agent intents (#148) and the
thread operations of scoped asks (#343).

This is the eventing layer over the durable project-level intent store. It owns
the two halves of the push-notify / pull-payload transport:

- **pull**: ``list_pending`` / ``next`` / ``resolve`` read and mutate the
  durable store, so a harness fetches the full payload on its own cadence.
- **push (signal only)**: after any change to the pending set - or to a
  thread - it publishes a lightweight ``IntentPending {count}`` event on the
  bus. Subscribers learn *that* something changed without paying for the
  payload on every turn.

Threads (#343): an intent carries host-encoded ``targets``, ``base_version``
and append-only ``items``. The host validates suggestions and applies or
reverts them. Item ``author`` is always the ambient actor (#322).

Pure core: it depends on store, host and count-signal ports and a clock,
never on a concrete adapter. Legacy origin field names remain in the records;
hosts and transport wrappers own the meaning of those identifiers.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from intent_layer.actor import SYSTEM_ACTOR, Actor, current_actor
from intent_layer.errors import SuggestionApplyError, ThreadError
from intent_layer.models import (
    INTENT_KINDS,
    PENDING,
    PLACE_STATES,
    PLACED_PLANNED,
    QUESTION_ANSWERED,
    RESOLVED,
    SUGGESTION_APPLIED,
    SUGGESTION_DECLINED,
    SUGGESTION_PENDING,
    SUGGESTION_REVERTED,
    SUGGESTION_SUPERSEDED,
    THREAD_ITEM_TYPES,
    Intent,
    IntentKind,
    ThreadItem,
    initial_item_state,
)
from intent_layer.ports import IntentStore, ThreadContext, ThreadHost
from intent_layer.signals import PendingSignal, PendingSignals
from intent_layer.target_json import copy_json_targets

#: Bus ``workspace_id`` used for the count signal when an intent has no
#: originating canvas. A project-level subscriber (or the global firehose)
#: still receives it; a per-canvas SSE stream filters on the canvas id.
PROJECT_SIGNAL_ID = "_project"


class UnknownIntentKindError(ValueError):
    """Raised when an enqueue uses a kind the queue does not recognize."""


def _validate_place(place: Any) -> dict[str, Any] | None:
    """``{x, y, width?, height?}`` as numbers, or None when not given.

    Malformed is refused, not coerced: a ghost drawn at ``NaN`` is a ghost
    nobody will ever find.
    """
    if place is None:
        return None
    if not isinstance(place, dict):
        raise ThreadError("invalid_item", "place must be an object {x, y, width?, height?}")
    out: dict[str, Any] = {}
    for key in ("x", "y"):
        if key not in place:
            raise ThreadError("invalid_item", f"place needs {key}")
    for key in ("x", "y", "width", "height"):
        if key not in place:
            continue
        value = place[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or math.isnan(value):
            raise ThreadError("invalid_item", f"place.{key} must be a number")
        out[key] = float(value)
    return out


class IntentService:
    """Thread transitions over explicit host and signal ports.

    Host mutation and persistence of thread state remain separate operations.
    Legacy field names are retained for persisted and adapter compatibility.
    """

    def __init__(
        self,
        store: IntentStore,
        bus: PendingSignals,
        *,
        now: Callable[[], float] | None = None,
        host: ThreadHost,
    ) -> None:
        self._store = store
        self._bus = bus
        self._now = now
        self._host = host

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
        targets: list[Any] | None = None,
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
        clean_targets = copy_json_targets(
            self._host.encode_targets(self._host.validate_targets(targets)),
        )
        base_version: int | None = None
        if origin_canvas_id is not None:
            base_version = await self._host.base_version(origin_canvas_id)
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
        place: dict[str, Any] | None = None,
        options: list[str] | None = None,
    ) -> tuple[Intent, ThreadItem]:
        """Append an item to a thread. ``author`` is the ambient actor.

        ``message`` / ``result`` need ``text``; ``question`` starts ``open``;
        ``suggestion`` needs a non-empty ``ops`` list and starts ``pending``.
        ``supersedes`` names an earlier suggestion in the same thread; if that
        one is still pending it becomes ``superseded``. Raises ``KeyError``
        for an unknown intent and :class:`ThreadError` for a bad item.

        ``place`` puts a ``message`` or ``question`` on the canvas at
        ``{x, y, width?, height?}``. A placed message is a ghost of work to
        come and starts ``planned``; see :func:`update_item` for moving it
        through ``active`` to ``done``.

        ``options`` are answers a ``question`` offers, so the human can reply
        with one press; free text is still accepted as an answer.
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
            clean_ops = self._host.validate_ops(ops)
        elif ops:
            raise ThreadError("invalid_item", "only a suggestion carries ops")
        if supersedes is not None and type != "suggestion":
            raise ThreadError("invalid_item", "only a suggestion can supersede another")
        clean_place = _validate_place(place)
        if clean_place is not None and type not in ("message", "question"):
            raise ThreadError(
                "invalid_item", "only a message or a question can be placed on the canvas",
            )
        clean_options: list[str] | None = None
        if options is not None:
            if type != "question":
                raise ThreadError("invalid_item", "only a question offers options")
            if not isinstance(options, list) or not all(
                isinstance(o, str) and o.strip() for o in options
            ):
                raise ThreadError("invalid_item", "options must be non-empty strings")
            seen: list[str] = []
            for o in options:
                if o.strip() not in seen:
                    seen.append(o.strip())
            clean_options = seen or None
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
            state=(
                PLACED_PLANNED
                if type == "message" and clean_place is not None
                else initial_item_state(type)
            ),
            ops=clean_ops,
            supersedes=supersedes,
            place=clean_place,
            options=clean_options,
        )
        intent.items.append(item)
        await self._store.replace(intent)
        await self._signal_pending(intent.origin_canvas_id)
        return intent, item

    async def update_item(
        self,
        intent_id: str,
        item_id: str,
        *,
        text: str | None = None,
        state: str | None = None,
        place: dict[str, Any] | None = None,
    ) -> tuple[Intent, ThreadItem]:
        """Change a ``message`` in place: its text, its state, or where it sits.

        Only messages. They are the one kind of item that describes work in
        progress, and progress is a thing that changes: "fetching page 3"
        becomes "found the measures table" without the thread growing a line
        for every step. A question's answer and a suggestion's verdict have
        their own verbs, and an item once applied is history.

        ``state`` must be one of ``planned`` / ``active`` / ``done`` and only
        means anything for a placed message; setting it on one with no place
        is refused rather than silently stored.
        """
        intent = await self._require(intent_id)
        item = self._require_item(intent, item_id)
        if item.type != "message":
            raise ThreadError("invalid_item", f"item {item_id!r} is a {item.type}, not a message")
        if text is not None:
            if not isinstance(text, str) or not text.strip():
                raise ThreadError("invalid_item", "a message needs text")
            item.text = text
        clean_place = _validate_place(place)
        if clean_place is not None:
            item.place = clean_place
            if item.state is None:
                item.state = PLACED_PLANNED
        if state is not None:
            if state not in PLACE_STATES:
                raise ThreadError(
                    "invalid_item", f"state must be one of {sorted(PLACE_STATES)}, not {state!r}",
                )
            if item.place is None:
                raise ThreadError("invalid_item", "only a placed message has a state")
            item.state = state
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
        self._host.ensure_available("apply")
        intent = await self._require(intent_id)
        item = self._require_item(intent, item_id)
        if item.type != "suggestion":
            raise ThreadError("not_a_suggestion", f"item {item_id!r} is a {item.type}")
        if item.state != SUGGESTION_PENDING:
            raise ThreadError("not_pending", f"suggestion {item_id!r} is {item.state}")
        application = await self._host.apply(self._context(intent, item), deepcopy(item.ops or []))
        item.state = SUGGESTION_APPLIED
        item.applied_versions = list(application.versions)
        item.undo_ops = deepcopy(application.undo)
        await self._store.replace(intent)
        await self._signal_pending(intent.origin_canvas_id)
        return intent, item, application.result

    async def revert_suggestion(
        self, intent_id: str, item_id: str,
    ) -> tuple[Intent, ThreadItem, dict[str, Any]]:
        """Put an applied suggestion back, all-or-nothing.

        The inverse ops were written down when it was applied, so this is
        the same batch path in the other direction: attributed to the actor
        putting it back, caused by the item. The item becomes ``reverted``.
        Refused for anything not currently ``applied``, and for a suggestion
        applied before undo was recorded -- there is nothing honest to do
        with those but say so.
        """
        self._host.ensure_available("revert")
        intent = await self._require(intent_id)
        item = self._require_item(intent, item_id)
        if item.type != "suggestion":
            raise ThreadError("not_a_suggestion", f"item {item_id!r} is a {item.type}")
        if item.state != SUGGESTION_APPLIED:
            raise ThreadError("not_applied", f"suggestion {item_id!r} is {item.state}")
        if not item.undo_ops:
            raise ThreadError(
                "no_undo", f"suggestion {item_id!r} was applied without a way back recorded",
            )
        result = await self._host.revert(self._context(intent, item), deepcopy(item.undo_ops))
        item.state = SUGGESTION_REVERTED
        await self._store.replace(intent)
        await self._signal_pending(intent.origin_canvas_id)
        return intent, item, result

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

    def _context(self, intent: Intent, item: ThreadItem) -> ThreadContext:
        return ThreadContext(
            intent_id=intent.id, origin_id=intent.origin_canvas_id,
            targets=copy_json_targets(self._host.decode_targets(deepcopy(intent.targets))),
            item_id=item.id,
            author=item.author, approver=self._actor(),
        )

    async def pending_count(self) -> int:
        return len(await self.list_pending())

    async def _signal_pending(self, origin_canvas_id: str | None) -> None:
        """Publish ``IntentPending {count}`` - count only, never the payload."""
        count = await self.pending_count()
        await self._bus.publish(
            PendingSignal(origin_id=origin_canvas_id, count=count, ts=self._ts()),
        )


__all__ = [
    "PROJECT_SIGNAL_ID",
    "IntentService",
    "SuggestionApplyError",
    "ThreadError",
    "UnknownIntentKindError",
]
