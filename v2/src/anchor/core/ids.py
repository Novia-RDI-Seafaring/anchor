"""Identifier helpers — pure, no I/O."""
from __future__ import annotations

import re
import uuid
from typing import NewType

DocId = NewType("DocId", str)
WorkspaceId = NewType("WorkspaceId", str)
NodeId = NewType("NodeId", str)
EdgeId = NewType("EdgeId", str)
EventId = NewType("EventId", str)


def slugify(name: str) -> str:
    """Lowercase, alphanumeric, hyphen-separated. Empty input → 'doc'."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower() or "doc"


def new_id() -> str:
    """8-char uuid4 fragment, matches the existing canvas convention."""
    return str(uuid.uuid4())[:8]


def new_event_id() -> str:
    """Full uuid4 for events — used as the idempotency key."""
    return str(uuid.uuid4())
