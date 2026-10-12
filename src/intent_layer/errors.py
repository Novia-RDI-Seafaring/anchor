"""Transport-independent thread rejection facts."""
from __future__ import annotations

from typing import Any, Protocol


class ThreadError(ValueError):
    """A stable code and authored message surfaced by all adapters."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        # Adapters surface this authored message, never exception rendering.
        self.message = message


class ApplicationFailure(Protocol):
    failing_index: int
    reason: str
    stale: bool


class SuggestionApplyError(ThreadError):
    """The host rejected a batch without changing its state."""

    def __init__(self, cause: ApplicationFailure) -> None:
        super().__init__("apply_failed", "suggestion could not be applied; nothing was changed")
        self.failing_index = cause.failing_index
        self.reason = cause.reason
        self.stale = cause.stale

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "failing_index": self.failing_index,
            "failing_op_index": self.failing_index,
            "reason": self.reason,
            "stale": self.stale,
        }
