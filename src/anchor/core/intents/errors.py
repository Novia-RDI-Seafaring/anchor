"""Compatibility imports for the independent intent layer."""
from intent_layer.errors import ApplicationFailure as ApplicationFailure
from intent_layer.errors import SuggestionApplyError as SuggestionApplyError
from intent_layer.errors import ThreadError as ThreadError

__all__ = [
    'ApplicationFailure',
    'SuggestionApplyError',
    'ThreadError',
]
