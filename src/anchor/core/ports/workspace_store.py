"""WorkspaceStore protocol — durable per-workspace state."""
from __future__ import annotations

from typing import Protocol

from anchor.core.events.envelope import DomainEvent
from anchor.core.workspace.workspace import Workspace, WorkspaceMeta


class WorkspaceStore(Protocol):
    async def list_workspaces(self) -> list[WorkspaceMeta]:
        raise NotImplementedError

    async def create(self, slug: str, title: str = "") -> WorkspaceMeta:
        raise NotImplementedError

    async def load(self, slug: str) -> Workspace:
        raise NotImplementedError

    async def append_event(self, slug: str, event: DomainEvent) -> int:
        """Persist event; return its assigned version. Idempotent on event.id."""
        raise NotImplementedError

    async def snapshot(self, slug: str, state: Workspace) -> None:
        """Write the current state as a replay checkpoint."""
        raise NotImplementedError
