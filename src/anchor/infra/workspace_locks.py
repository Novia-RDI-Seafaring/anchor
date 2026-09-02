"""In-process implementation of per-workspace mutation locks."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager


class InProcessWorkspaceLocks:
    """Serialize writes per workspace without blocking unrelated workspaces."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, workspace_id: str) -> AbstractAsyncContextManager[None]:
        return self._locks.setdefault(workspace_id, asyncio.Lock())
