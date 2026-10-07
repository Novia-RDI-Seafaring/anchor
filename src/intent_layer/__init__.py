"""Host-independent intent threads, shipped inside anchor-kb.

Transport adapters are opt-in imports; importing this package needs no Anchor.
"""
from intent_layer.actor import Actor, actor_scope, current_actor
from intent_layer.models import Intent, ThreadItem
from intent_layer.ports import AppliedSuggestion, ThreadContext, ThreadHost
from intent_layer.service import IntentService

__all__ = ["Actor", "AppliedSuggestion", "Intent", "IntentService", "ThreadContext", "ThreadHost", "ThreadItem", "actor_scope", "current_actor"]
