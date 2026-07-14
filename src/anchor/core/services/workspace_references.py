"""Canvas-scoped bibliography operations for ``WorkspaceService``."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel

from anchor.core.clock import Clock
from anchor.core.events.canvas import (
    ReferenceAttached,
    ReferenceCreated,
    ReferenceRemoved,
    ReferenceUpdated,
)
from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import new_id
from anchor.core.ports.workspace_store import WorkspaceStore
from anchor.core.services.workspace_operation_support import WorkspaceLocks
from anchor.core.workspace.references import (
    Reference,
    ReferenceError,
    validate_source_ref,
)
from anchor.core.workspace.workspace import CommandError, Workspace

DispatchLocked = Callable[
    [str, BaseModel],
    Awaitable[tuple[Workspace, DomainEvent]],
]


class WorkspaceReferenceOperations:
    """Own reference validation, lookup, and bibliography commands."""

    def __init__(
        self,
        store: WorkspaceStore,
        locks: WorkspaceLocks,
        clock: Clock,
        dispatch_locked: DispatchLocked,
    ) -> None:
        self.store = store
        self.locks = locks
        self.clock = clock
        self.dispatch_locked = dispatch_locked

    async def create(
        self,
        slug: str,
        *,
        source_ref: dict[str, Any],
        label: str | None = None,
        created_by: str = "human",
    ) -> dict[str, Any]:
        try:
            validated = validate_source_ref(source_ref)
        except ReferenceError as exc:
            raise CommandError(str(exc)) from exc
        if created_by not in ("human", "agent"):
            raise CommandError(
                f"created_by must be 'human' or 'agent', got {created_by!r}",
            )

        reference = Reference(
            id=new_id(),
            label=label,
            source_ref=validated,
            created_by=created_by,
            created_at=self.clock.now(),
        )
        stored = reference.model_dump()
        async with self.locks.lock(slug):
            await self.store.load(slug)
            await self.dispatch_locked(slug, ReferenceCreated(reference=stored))
        return stored

    async def list(self, slug: str) -> list[dict[str, Any]]:
        state = await self.store.load(slug)
        references = state.metadata.get("references")
        if not isinstance(references, list):
            return []
        return [dict(item) for item in references if isinstance(item, dict)]

    async def attach(
        self,
        slug: str,
        reference_id: str,
        *,
        node_id: str,
        row_index: int | None = None,
    ) -> tuple[Workspace, DomainEvent]:
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            reference = self._find(state.metadata.get("references"), reference_id)
            if reference is None:
                raise CommandError(f"reference {reference_id!r} does not exist")
            command = ReferenceAttached(
                reference_id=reference_id,
                node_id=node_id,
                row_index=row_index,
                source_ref=dict(reference.get("source_ref") or {}),
            )
            return await self.dispatch_locked(slug, command)

    async def remove(
        self,
        slug: str,
        reference_id: str,
    ) -> tuple[Workspace, DomainEvent]:
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            if self._find(state.metadata.get("references"), reference_id) is None:
                raise CommandError(f"reference {reference_id!r} does not exist")
            return await self.dispatch_locked(
                slug,
                ReferenceRemoved(reference_id=reference_id),
            )

    async def update(
        self,
        slug: str,
        reference_id: str,
        *,
        label: str | None = None,
    ) -> tuple[Workspace, DomainEvent]:
        async with self.locks.lock(slug):
            state = await self.store.load(slug)
            if self._find(state.metadata.get("references"), reference_id) is None:
                raise CommandError(f"reference {reference_id!r} does not exist")
            return await self.dispatch_locked(
                slug,
                ReferenceUpdated(reference_id=reference_id, label=label),
            )

    @staticmethod
    def _find(references: Any, reference_id: str) -> dict[str, Any] | None:
        if not isinstance(references, list):
            return None
        return next(
            (
                item
                for item in references
                if isinstance(item, dict) and item.get("id") == reference_id
            ),
            None,
        )
