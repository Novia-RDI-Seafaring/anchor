"""In-process implementation of per-workspace mutation locks."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from pathlib import Path


class InProcessWorkspaceLocks:
    """Serialize writes per workspace without blocking unrelated workspaces."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def lock(self, workspace_id: str) -> AbstractAsyncContextManager[None]:
        existing = self._locks.get(workspace_id)
        if existing is None:
            # setdefault (not assignment) so a racing first caller still
            # converges on one lock; the get() above avoids allocating a
            # throwaway Lock on every cache hit (#272 minor).
            existing = self._locks.setdefault(workspace_id, asyncio.Lock())
        return existing


# Process-level registry: one lock map per project data dir, shared by every
# runtime bundle built for that dir. Locks are effectively keyed by
# (data_dir, workspace slug). The MCP router caches runtime bundles in a
# small LRU; if the registry lived inside the bundle, evicting and
# re-resolving a project mid-write would hand a second writer a fresh lock
# and defeat serialization (#272). Entries are tiny and bounded by the number
# of distinct projects touched in one process, so they are never evicted.
_PROCESS_LOCKS: dict[str, InProcessWorkspaceLocks] = {}


def process_workspace_locks(data_dir: Path) -> InProcessWorkspaceLocks:
    """Return the process-wide lock registry for one project data dir.

    Every caller that composes a runtime for ``data_dir`` gets the same
    registry object, so two bundles built for the same project (for example
    before and after an LRU eviction) serialize writers on the same locks.
    """
    key = str(Path(data_dir).resolve())
    registry = _PROCESS_LOCKS.get(key)
    if registry is None:
        registry = _PROCESS_LOCKS.setdefault(key, InProcessWorkspaceLocks())
    return registry
