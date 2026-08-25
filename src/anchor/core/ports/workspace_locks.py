"""Per-workspace mutation serialization port."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol


class WorkspaceLocks(Protocol):
    """Provide an async critical section for one workspace."""

    def lock(self, workspace_id: str) -> AbstractAsyncContextManager[None]:
        """Return a context manager that serializes writes to the workspace."""
        pass
