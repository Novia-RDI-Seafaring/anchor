"""Shared structural types for workspace operation collaborators."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Protocol


class WorkspaceLocks(Protocol):
    """Per-workspace lock provider used by state-changing services."""

    def lock(self, workspace_id: str) -> AbstractAsyncContextManager[None]:
        raise NotImplementedError
