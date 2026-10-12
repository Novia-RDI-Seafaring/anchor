"""Compatibility imports for the independent intent layer."""
from intent_layer.ports import AppliedSuggestion as AppliedSuggestion
from intent_layer.ports import ThreadContext as ThreadContext
from intent_layer.ports import ThreadHost as ThreadHost

__all__ = [
    'AppliedSuggestion',
    'ThreadContext',
    'ThreadHost',
]
