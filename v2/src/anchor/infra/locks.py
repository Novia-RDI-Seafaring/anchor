"""Per-workspace asyncio locks. Pure infra — no transport, no I/O."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


class WorkspaceLocks:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def lock(self, workspace_id: str):
        async with self._guard:
            lock = self._locks.setdefault(workspace_id, asyncio.Lock())
        async with lock:
            yield
