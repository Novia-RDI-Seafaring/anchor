"""In-memory store implementations — used by tests and ephemeral mode."""
from __future__ import annotations

import asyncio
import time

from anchor.core.events.envelope import DomainEvent
from anchor.core.workspace.workspace import Workspace, WorkspaceMeta


class MemoryWorkspaceStore:
    def __init__(self) -> None:
        self._meta: dict[str, WorkspaceMeta] = {}
        self._snapshots: dict[str, Workspace] = {}
        self._events: dict[str, list[DomainEvent]] = {}
        self._versions: dict[str, int] = {}
        self._seen_ids: dict[str, dict[str, int]] = {}
        self._lock = asyncio.Lock()

    async def list_workspaces(self) -> list[WorkspaceMeta]:
        return list(self._meta.values())

    async def create(self, slug: str, title: str = "") -> WorkspaceMeta:
        async with self._lock:
            if slug in self._meta:
                return self._meta[slug]
            meta = WorkspaceMeta(slug=slug, title=title or slug, created_at=time.time())
            self._meta[slug] = meta
            self._snapshots[slug] = Workspace(slug=slug, title=meta.title)
            self._events[slug] = []
            self._versions[slug] = 0
            self._seen_ids[slug] = {}
            return meta

    async def load(self, slug: str) -> Workspace:
        if slug not in self._snapshots:
            await self.create(slug)
        return self._snapshots[slug].model_copy(deep=True)

    async def append_event(self, slug: str, event: DomainEvent) -> int:
        async with self._lock:
            if slug not in self._events:
                await self.create(slug)
            seen = self._seen_ids[slug]
            if event.id in seen:
                return seen[event.id]
            self._versions[slug] += 1
            event.version = self._versions[slug]
            event.workspace_id = slug
            self._events[slug].append(event)
            seen[event.id] = event.version
            return event.version

    async def snapshot(self, slug: str, state: Workspace) -> None:
        async with self._lock:
            self._snapshots[slug] = state.model_copy(deep=True)

    async def get_events(self, slug: str) -> list[DomainEvent]:
        return list(self._events.get(slug, []))


