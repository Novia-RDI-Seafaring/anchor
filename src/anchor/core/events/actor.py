"""Compatibility imports for the independent intent layer."""
import os

from intent_layer.actor import SYSTEM_ACTOR as SYSTEM_ACTOR
from intent_layer.actor import Actor as Actor
from intent_layer.actor import ActorKind as ActorKind
from intent_layer.actor import actor_scope as actor_scope
from intent_layer.actor import current_actor as current_actor
from intent_layer.actor import parse_actor as parse_actor
from intent_layer.actor import reset_current_actor as reset_current_actor
from intent_layer.actor import resolve_cli_actor as _resolve_cli_actor
from intent_layer.actor import set_current_actor as set_current_actor


def resolve_cli_actor(flag: str | None = None, env: str | None = None) -> Actor:
    """Retain Anchor's CLI environment default over the shared actor context."""
    return _resolve_cli_actor(flag, env if env is not None else os.environ.get("ANCHOR_AGENT"))

__all__ = [
    'SYSTEM_ACTOR',
    'Actor',
    'ActorKind',
    'actor_scope',
    'current_actor',
    'parse_actor',
    'reset_current_actor',
    'set_current_actor',
    'resolve_cli_actor',
]
