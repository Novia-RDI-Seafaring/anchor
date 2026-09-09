"""Actor attribution: who caused a canvas event (#322).

Every ``DomainEvent`` may carry an ``Actor`` naming the party behind the
write: a ``human`` (browser, CLI user), an ``agent`` (MCP client, scripted
CLI), or the ``system`` itself (cascade events like the ``EdgeRemoved``
fan-out of a ``NodeRemoved``). The field is additive and optional — events
recorded before #322 deserialize with ``actor=None`` and replay unchanged.

Adapters stamp a default actor at their boundary via a ``ContextVar`` so
core service code never needs an ``actor=`` parameter threaded through
every write method:

- HTTP: middleware sets ``human``/"browser" per request (body may override).
- MCP: ``handlers_canvas.call_tool`` sets ``agent`` with the MCP client
  name as label when the server session exposes one.
- CLI: the ``anchor canvas`` callback sets ``human``/"cli", or ``agent``
  when ``ANCHOR_AGENT`` is set / ``--actor`` is given.

``WorkspaceService`` reads the context at envelope-build time; cascades
override it with ``SYSTEM_ACTOR`` while preserving ``causation_id``.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Literal

from pydantic import BaseModel

ActorKind = Literal["human", "agent", "system"]

_KINDS: tuple[str, ...] = ("human", "agent", "system")


class Actor(BaseModel):
    """The party responsible for an event. ``kind`` is required; ``id``
    (a stable identity, unused until auth lands) and ``label`` (a display
    name like "browser", "claude-code", "cli") are optional."""

    kind: ActorKind
    id: str | None = None
    label: str | None = None


SYSTEM_ACTOR = Actor(kind="system")

_current_actor: ContextVar[Actor | None] = ContextVar(
    "anchor_current_actor", default=None,
)


def current_actor() -> Actor | None:
    """The actor the enclosing adapter attributed this call to (or None)."""
    return _current_actor.get()


def set_current_actor(actor: Actor | None) -> Token[Actor | None]:
    """Set the ambient actor; returns the token for ``reset_current_actor``."""
    return _current_actor.set(actor)


def reset_current_actor(token: Token[Actor | None]) -> None:
    _current_actor.reset(token)


@contextmanager
def actor_scope(actor: Actor | None) -> Iterator[None]:
    """Attribute every write inside the block to ``actor``."""
    token = _current_actor.set(actor)
    try:
        yield
    finally:
        _current_actor.reset(token)


def parse_actor(spec: str) -> Actor:
    """Parse a ``kind[:label]`` string (the CLI ``--actor`` flag).

    ``"agent"`` → Actor(kind="agent"); ``"agent:claude"`` → label "claude".
    Raises ``ValueError`` on an unknown kind so the CLI can exit(2).
    """
    kind, sep, label = spec.partition(":")
    kind = kind.strip()
    if kind not in _KINDS:
        raise ValueError(
            f"unknown actor kind {kind!r} (use one of {', '.join(_KINDS)}, "
            "optionally as 'kind:label')",
        )
    label = label.strip()
    return Actor(kind=kind, label=label or None)  # type: ignore[arg-type]


_TRUTHY_SWITCHES = {"1", "true", "yes", "on"}


def resolve_cli_actor(flag: str | None = None, env: str | None = None) -> Actor:
    """Resolve the CLI's actor: ``--actor`` wins, then ``ANCHOR_AGENT``,
    then the human-at-a-terminal default.

    ``ANCHOR_AGENT=1`` (or any bare switch value) yields ``agent`` with no
    label; a descriptive value (``ANCHOR_AGENT=claude-code``) becomes the
    label.
    """
    if flag:
        return parse_actor(flag)
    env = env if env is not None else os.environ.get("ANCHOR_AGENT")
    if env:
        label = None if env.strip().lower() in _TRUTHY_SWITCHES else env.strip()
        return Actor(kind="agent", label=label)
    return Actor(kind="human", label="cli")
