"""EventBus protocol — pub-sub for domain events."""
from __future__ import annotations

from typing import AsyncIterator, Protocol

from anchor.core.events.envelope import DomainEvent


class EventBus(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...

    def subscribe(self, workspace_id: str | None = None) -> AsyncIterator[DomainEvent]:
        """Iterate events. None = global firehose; otherwise per-workspace."""
        ...
