"""Atomic batch apply for staged suggestions (#343).

A thread ``suggestion`` is a list of ops in the canvas event vocabulary
(``NodeAdded`` / ``NodeUpdated`` / ``NodeRemoved`` / ``EdgeAdded`` /
``EdgeUpdated`` / ``EdgeRemoved``). Approving it applies the whole list or
nothing:

1. **Plan** every op against a *copy* of the current state through the
   reducer. A ``NodeAdded`` / ``EdgeAdded`` may carry a client id; it is
   mapped to a freshly minted real id and every later op in the batch that
   references the client id is rewritten. An op that references an element
   the state no longer has fails as *stale*; any other invariant violation
   fails as *invalid*. The first failure aborts with its index and reason
   and nothing has been written.
2. **Emit** the planned commands through the same envelope / append /
   reduce / snapshot / publish path every other write uses, under the
   workspace lock, so SSE, attribution, and the event log behave as for any
   write. The actor is the suggestion's author; ``causation_id`` is the item
   id so ``canvas_changes`` can group what one suggestion did. A
   ``NodeRemoved`` fans out its ``EdgeRemoved`` cascade exactly as
   ``remove_node`` does (attributed to ``system``).

Elements the batch creates are stamped ``data.review = {state: "accepted",
by: <approver>, at}``: approval *is* the review.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from anchor.core.clock import Clock
from anchor.core.events.actor import SYSTEM_ACTOR, Actor
from anchor.core.events.canvas import (
    EdgeAdded,
    EdgeRemoved,
    EdgeUpdated,
    NodeAdded,
    NodeRemoved,
    NodeUpdated,
)
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_id
from anchor.core.ports.event_bus import EventBus
from anchor.core.ports.workspace_locks import WorkspaceLocks
from anchor.core.ports.workspace_store import WorkspaceStore
from anchor.core.workspace.node_types import NodeTypeRegistry
from anchor.core.workspace.reducer import apply, cascade_events_for_remove
from anchor.core.workspace.review import accepted_review
from anchor.core.workspace.workspace import CommandError, Workspace, validate_command

logger = logging.getLogger(__name__)

_OP_CLASSES: dict[str, type[BaseModel]] = {
    "NodeAdded": NodeAdded,
    "NodeUpdated": NodeUpdated,
    "NodeRemoved": NodeRemoved,
    "EdgeAdded": EdgeAdded,
    "EdgeUpdated": EdgeUpdated,
    "EdgeRemoved": EdgeRemoved,
}

#: Builds the envelope for one command (``WorkspaceService._envelope``).
EnvelopeBuilder = Callable[..., DomainEvent]


class BatchApplyError(CommandError):
    """One op in a batch failed planning; nothing was applied.

    ``failing_index`` is the op's position in the batch, ``reason`` the
    human-readable cause, ``stale`` whether the op referenced an element
    that no longer exists (the UI shows such a suggestion as stale).
    """

    def __init__(self, failing_index: int, reason: str, *, stale: bool = False) -> None:
        super().__init__(f"op {failing_index}: {reason}")
        self.failing_index = failing_index
        self.reason = reason
        self.stale = stale

    def to_dict(self) -> dict[str, Any]:
        return {
            "failing_index": self.failing_index,
            "reason": self.reason,
            "stale": self.stale,
        }


class WorkspaceBatchOperations:
    def __init__(
        self,
        store: WorkspaceStore,
        bus: EventBus,
        locks: WorkspaceLocks,
        clock: Clock,
        node_types: NodeTypeRegistry | None,
        envelope: EnvelopeBuilder,
        prepare_command: Callable[[Workspace, BaseModel], Awaitable[BaseModel]],
    ) -> None:
        self._store = store
        self._bus = bus
        self._locks = locks
        self._clock = clock
        self._node_types = node_types
        self._envelope = envelope
        self._prepare_command = prepare_command

    async def apply(
        self,
        slug: str,
        ops: list[dict[str, Any]],
        *,
        actor: Actor,
        causation_id: str,
        approver: Actor,
    ) -> tuple[Workspace, list[DomainEvent], dict[str, str]]:
        """Apply ``ops`` all-or-nothing. Returns the new state, the emitted
        envelopes (in order, cascades included) and the client-id -> real-id
        map. Raises :class:`BatchApplyError` (a ``CommandError``) when any op
        fails planning; the canvas is untouched in that case."""
        if not ops:
            raise CommandError("suggestion has no ops")
        async with self._locks.lock(slug):
            state = await self._store.load(slug)
            planned, id_map = await self._plan(state, ops, approver=approver)
            envelopes: list[DomainEvent] = []
            new_state = state
            for cmd, override in planned:
                env = self._envelope(
                    slug, cmd, causation_id=causation_id,
                    actor=override if override is not None else actor,
                )
                version = await self._store.append_event(slug, env)
                env.version = version
                new_state = apply(new_state, cmd)
                new_state.version = version
                new_state.last_event_id = env.id
                envelopes.append(env)
            await self._store.snapshot(slug, new_state)
            for env in envelopes:
                await self._bus.publish(env)
            return new_state, envelopes, id_map

    # -- planning ---------------------------------------------------------- #
    async def _plan(
        self,
        state: Workspace,
        ops: list[dict[str, Any]],
        *,
        approver: Actor,
    ) -> tuple[list[tuple[BaseModel, Actor | None]], dict[str, str]]:
        """Validate every op on a copy of ``state``; return the commands to
        emit (with an actor override for cascades) and the id map."""
        sim = state
        id_map: dict[str, str] = {}
        planned: list[tuple[BaseModel, Actor | None]] = []
        stamp = accepted_review(approver, self._clock.now())
        for index, op in enumerate(ops):
            cmd = self._build(index, op, sim, id_map, stamp)
            try:
                cmd = await self._prepare_command(sim, cmd)
                validate_command(sim, cmd, node_types=self._node_types)
            except CommandError as exc:
                # The reason returned to clients is templated from the op
                # itself, not from the exception text, so no exception-derived
                # string reaches a response; the precise reducer message goes
                # to the server log for debugging.
                logger.info("suggestion op %d (%s) rejected: %s", index, type(cmd).__name__, exc)
                raise BatchApplyError(
                    index, f"op {index} ({type(cmd).__name__}) was rejected by the canvas"
                ) from exc
            if isinstance(cmd, NodeRemoved):
                for cascade in cascade_events_for_remove(sim, cmd.id):
                    planned.append((cascade, SYSTEM_ACTOR))
                    sim = apply(sim, cascade)
            planned.append((cmd, None))
            sim = apply(sim, cmd)
        return planned, id_map

    def _build(
        self,
        index: int,
        op: Any,
        sim: Workspace,
        id_map: dict[str, str],
        stamp: dict[str, Any],
    ) -> BaseModel:
        if not isinstance(op, dict):
            raise BatchApplyError(index, "op must be an object {type, payload}")
        op_type = op.get("type")
        cls = _OP_CLASSES.get(op_type) if isinstance(op_type, str) else None
        if cls is None:
            raise BatchApplyError(
                index,
                f"unknown op type {op_type!r}; expected one of "
                f"{', '.join(_OP_CLASSES)}",
            )
        raw = op.get("payload")
        if not isinstance(raw, dict):
            raise BatchApplyError(index, "op payload must be an object")
        payload: dict[str, Any] = dict(raw)

        def resolve(value: Any) -> Any:
            return id_map.get(value, value) if isinstance(value, str) else value

        if cls is NodeAdded:
            client_id = payload.get("id")
            real_id = new_id()
            if isinstance(client_id, str) and client_id:
                id_map[client_id] = real_id
            payload["id"] = real_id
            if payload.get("parent") is not None:
                payload["parent"] = resolve(payload["parent"])
                if payload["parent"] not in sim.nodes:
                    raise BatchApplyError(
                        index, f"parent {payload['parent']!r} does not exist", stale=True,
                    )
            payload["data"] = self._stamped(payload.get("data"), stamp, index)
        elif cls is EdgeAdded:
            client_id = payload.get("id")
            real_id = new_id()
            if isinstance(client_id, str) and client_id:
                id_map[client_id] = real_id
            payload["id"] = real_id
            for end in ("source", "target"):
                payload[end] = resolve(payload.get(end))
                if payload[end] not in sim.nodes:
                    raise BatchApplyError(
                        index, f"edge {end} {payload[end]!r} does not exist", stale=True,
                    )
            payload["data"] = self._stamped(payload.get("data"), stamp, index)
        elif cls in (NodeUpdated, NodeRemoved):
            payload["id"] = resolve(payload.get("id"))
            if payload["id"] not in sim.nodes:
                raise BatchApplyError(
                    index, f"node {payload['id']!r} does not exist", stale=True,
                )
        else:  # EdgeUpdated / EdgeRemoved
            payload["id"] = resolve(payload.get("id"))
            if payload["id"] not in sim.edges:
                raise BatchApplyError(
                    index, f"edge {payload['id']!r} does not exist", stale=True,
                )
        try:
            return cls.model_validate(payload)
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            loc = ".".join(str(p) for p in first.get("loc", ())) or "payload"
            raise BatchApplyError(
                index, f"invalid {op_type} payload at {loc}: {first.get('msg', 'invalid')}",
            ) from exc

    @staticmethod
    def _stamped(data: Any, stamp: dict[str, Any], index: int) -> dict[str, Any]:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise BatchApplyError(index, "payload.data must be an object")
        return {**data, "review": dict(stamp)}
