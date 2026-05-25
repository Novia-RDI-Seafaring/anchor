"""DomainEvent envelope — every mutation in the system is one of these."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from anchor.core.ids import new_event_id


class DomainEvent(BaseModel):
    """An event accepted by the workspace.

    `id` is the client-generated idempotency key (server dedups on resubmit).
    `version` is the server-assigned monotonic per-workspace counter.
    `causation_id` traces cascades (NodeRemoved → multiple EdgeRemoved).
    """

    id: str = Field(default_factory=new_event_id)
    ts: float = 0.0
    version: int = 0
    workspace_id: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    causation_id: str | None = None

    model_config = {"frozen": False}
