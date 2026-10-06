"""Host-owned targets and suggestion application, independent of canvas commands."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import JsonValue

from anchor.core.events.actor import Actor


@dataclass(frozen=True)
class ThreadContext:
    intent_id: str
    origin_id: str | None
    targets: list[JsonValue]
    item_id: str
    author: Actor
    approver: Actor


@dataclass(frozen=True)
class AppliedSuggestion:
    undo: list[dict[str, Any]]
    versions: list[int]
    result: dict[str, Any]


class ThreadHost(Protocol):
    """Own target codecs, command validation and state mutation.

    The service persists encoded JSON targets unchanged. It never interprets
    host identifiers. Availability is checked before thread lookup to preserve
    each host's rejection precedence. Atomicity belongs to the host; persisting
    the thread after application is a separate operation.
    """

    def ensure_available(self, operation: str) -> None:
        raise NotImplementedError

    def validate_targets(self, raw: Any) -> list[JsonValue]:
        raise NotImplementedError

    def encode_targets(self, targets: list[JsonValue]) -> list[JsonValue]:
        raise NotImplementedError

    def decode_targets(self, raw: list[JsonValue]) -> list[JsonValue]:
        raise NotImplementedError

    def validate_ops(self, raw: Any) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def base_version(self, origin_id: str) -> int | None:
        raise NotImplementedError

    async def apply(self, context: ThreadContext, ops: list[dict[str, Any]]) -> AppliedSuggestion:
        raise NotImplementedError

    async def revert(self, context: ThreadContext, undo: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError
