"""Proposal-set operations for ``WorkspaceService`` (#359).

Grouping is one event (the set record names its members). A verdict is the
ordinary per-element review write applied to every member under one lock,
so every reader that already understands ``data.review`` needs no change.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from anchor.core.clock import Clock
from anchor.core.events.actor import SYSTEM_ACTOR, Actor
from anchor.core.events.canvas import (
    EdgeRemoved,
    EdgeUpdated,
    NodeRemoved,
    NodeUpdated,
    ProposalSetMembersAdded,
    ProposalSetOpened,
    ProposalSetReviewed,
)
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_id
from anchor.core.ports.event_bus import EventBus
from anchor.core.ports.workspace_locks import WorkspaceLocks
from anchor.core.ports.workspace_store import WorkspaceStore
from anchor.core.workspace.proposals import (
    ProposalSetError,
    actor_ref,
    find_set,
    list_sets,
    validate_members,
)
from anchor.core.workspace.reducer import apply, cascade_events_for_remove
from anchor.core.workspace.workspace import Workspace

Envelope = Callable[..., DomainEvent]
DispatchLocked = Callable[..., Awaitable[tuple[Workspace, DomainEvent]]]


class WorkspaceProposalOperations:
    """Own the grouping and the whole-set verdict."""

    def __init__(
        self,
        store: WorkspaceStore,
        bus: EventBus,
        locks: WorkspaceLocks,
        clock: Clock,
        envelope: Envelope,
        dispatch_locked: DispatchLocked,
    ) -> None:
        self.store = store
        self.bus = bus
        self.locks = locks
        self.clock = clock
        self._envelope = envelope
        self.dispatch_locked = dispatch_locked

    async def open(
        self,
        slug: str,
        *,
        reason: str,
        members: Any = None,
        actor: Actor | None = None,
    ) -> dict[str, Any]:
        """Group elements into one reviewable set and return the record.

        ``reason`` is required: a set that cannot say why it exists is not
        worth reviewing as a unit. Members may be named here or added later
        (an agent that draws first and groups after names them here).
        """
        text = (reason or "").strip()
        if not text:
            raise ProposalSetError("a proposal set needs a reason")
        validated = validate_members(members)
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            self._require_exist(state, validated)
            record = {
                "id": new_id(),
                "reason": text,
                "by": actor_ref(actor),
                "at": self.clock.now(),
                "members": validated,
                "state": "open",
            }
            await self.dispatch_locked(
                slug, ProposalSetOpened(proposal_set=record), state=state,
            )
        return record

    async def add_members(
        self, slug: str, set_id: str, *, members: Any,
    ) -> dict[str, Any]:
        """Add elements to an open set. Re-adding a member is a no-op."""
        validated = validate_members(members)
        if not validated:
            raise ProposalSetError("no members given")
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            record = self._require_set(state, set_id)
            if record.get("state") != "open":
                raise ProposalSetError(
                    f"proposal set {set_id!r} is already {record.get('state')}",
                )
            self._require_exist(state, validated)
            new_state, _ = await self.dispatch_locked(
                slug,
                ProposalSetMembersAdded(set_id=set_id, members=validated),
                state=state,
            )
            return self._require_set(new_state, set_id)

    async def list(self, slug: str, *, state_filter: str | None = None) -> list[dict[str, Any]]:
        """Every set on this canvas, oldest first, optionally by state."""
        state = await self.store.load(slug)
        sets = list_sets(state.metadata)
        if state_filter is None:
            return sets
        return [s for s in sets if s.get("state") == state_filter]

    async def get(self, slug: str, set_id: str) -> dict[str, Any]:
        state = await self.store.load(slug)
        return self._require_set(state, set_id)

    async def review(
        self,
        slug: str,
        set_id: str,
        *,
        verdict: str,
        discard: bool = False,
        except_ids: list[str] | None = None,
        actor: Actor | None = None,
    ) -> tuple[Workspace, list[DomainEvent], dict[str, Any]]:
        """Accept or reject a whole set in one write.

        ``accepted`` / ``rejected`` stamp ``data.review.state`` on every
        member that still exists. ``discard`` (rejections only) removes the
        members instead, which is the clean undo for a batch nobody wants:
        removing a node cascades its edges. ``except_ids`` leaves those
        members untouched, so "accept all but these two" is one call.
        """
        if verdict not in ("accepted", "rejected"):
            raise ProposalSetError(
                f"verdict must be 'accepted' or 'rejected', got {verdict!r}",
            )
        if discard and verdict != "rejected":
            raise ProposalSetError("only a rejected set can be discarded")
        skip = set(except_ids or ())
        at = self.clock.now()
        by = actor_ref(actor)
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            record = self._require_set(state, set_id)
            if record.get("state") != "open":
                raise ProposalSetError(
                    f"proposal set {set_id!r} is already {record.get('state')}",
                )
            # (command, is_cascade) pairs. `working` mirrors the state the
            # commands have been planned against, so a discard knows which
            # edges a previous member's removal already took.
            commands: list[tuple[BaseModel, bool]] = []
            working = state
            review = {"state": verdict, "by": by, "at": at}
            for member in record.get("members", []):
                kind = member.get("kind")
                ident = member.get("id")
                if not isinstance(ident, str) or ident in skip:
                    continue
                if kind == "node":
                    if ident not in state.nodes:
                        continue  # already gone: nothing to stamp
                    if discard:
                        # Removing a node drops its edges too. Emit those
                        # EdgeRemoved events explicitly (attributed to the
                        # system, as elsewhere) so every listener sees the
                        # cascade rather than inferring it.
                        for cascade in cascade_events_for_remove(working, ident):
                            commands.append((cascade, True))
                            working = apply(working, cascade)
                        commands.append((NodeRemoved(id=ident), False))
                        working = apply(working, NodeRemoved(id=ident))
                    else:
                        commands.append(
                            (NodeUpdated(id=ident, fields={"data": {"review": review}}), False),
                        )
                elif kind == "edge":
                    if ident not in working.edges:
                        continue  # a cascade above may have taken it already
                    if discard:
                        commands.append((EdgeRemoved(id=ident), False))
                        working = apply(working, EdgeRemoved(id=ident))
                    else:
                        commands.append(
                            (EdgeUpdated(id=ident, fields={"data": {"review": review}}), False),
                        )
            commands.append(
                (
                    ProposalSetReviewed(
                        set_id=set_id, state=verdict, by=by, at=at, discarded=discard,
                    ),
                    False,
                ),
            )
            envelopes: list[DomainEvent] = []
            new_state = state
            for cmd, is_cascade in commands:
                env = self._envelope(
                    slug,
                    cmd,
                    causation_id=set_id,
                    actor=SYSTEM_ACTOR if is_cascade else actor,
                )
                version = await self.store.append_event(slug, env)
                env.version = version
                new_state = apply(new_state, cmd)
                new_state.version = version
                new_state.last_event_id = env.id
                envelopes.append(env)
            await self.store.snapshot(slug, new_state)
            for env in envelopes:
                await self.bus.publish(env)
            return new_state, envelopes, self._require_set(new_state, set_id)

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _require_set(state: Workspace, set_id: str) -> dict[str, Any]:
        record = find_set(state.metadata, set_id)
        if record is None:
            raise ProposalSetError(f"unknown proposal set: {set_id!r}")
        return record

    @staticmethod
    def _require_exist(state: Workspace, members: list[dict[str, str]]) -> None:
        missing = [
            f"{m['kind']} {m['id']}"
            for m in members
            if (m["kind"] == "node" and m["id"] not in state.nodes)
            or (m["kind"] == "edge" and m["id"] not in state.edges)
        ]
        if missing:
            raise ProposalSetError("no such element: " + ", ".join(sorted(missing)))
