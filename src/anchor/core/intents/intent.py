"""Compatibility imports for the independent intent layer."""
from intent_layer.models import INTENT_KINDS as INTENT_KINDS
from intent_layer.models import INTENT_PENDING_EVENT as INTENT_PENDING_EVENT
from intent_layer.models import PENDING as PENDING
from intent_layer.models import PLACE_STATES as PLACE_STATES
from intent_layer.models import PLACED_ACTIVE as PLACED_ACTIVE
from intent_layer.models import PLACED_DONE as PLACED_DONE
from intent_layer.models import PLACED_PLANNED as PLACED_PLANNED
from intent_layer.models import QUESTION_ANSWERED as QUESTION_ANSWERED
from intent_layer.models import QUESTION_OPEN as QUESTION_OPEN
from intent_layer.models import RESOLVED as RESOLVED
from intent_layer.models import SUGGESTION_APPLIED as SUGGESTION_APPLIED
from intent_layer.models import SUGGESTION_DECLINED as SUGGESTION_DECLINED
from intent_layer.models import SUGGESTION_PENDING as SUGGESTION_PENDING
from intent_layer.models import SUGGESTION_REVERTED as SUGGESTION_REVERTED
from intent_layer.models import SUGGESTION_SUPERSEDED as SUGGESTION_SUPERSEDED
from intent_layer.models import THREAD_ITEM_TYPES as THREAD_ITEM_TYPES
from intent_layer.models import Intent as Intent
from intent_layer.models import IntentKind as IntentKind
from intent_layer.models import ThreadItem as ThreadItem
from intent_layer.models import ThreadItemType as ThreadItemType
from intent_layer.models import initial_item_state as initial_item_state

#: The canvas event vocabulary a suggestion's ops may use. Apply reuses the
#: workspace reducer, so no new mutation code exists for suggestions.
SUGGESTION_OP_TYPES: tuple[str, ...] = (
    "NodeAdded",
    "NodeUpdated",
    "NodeRemoved",
    "EdgeAdded",
    "EdgeUpdated",
    "EdgeRemoved",
)

__all__ = [
    'INTENT_KINDS',
    'INTENT_PENDING_EVENT',
    'PENDING',
    'PLACE_STATES',
    'PLACED_ACTIVE',
    'PLACED_DONE',
    'PLACED_PLANNED',
    'QUESTION_ANSWERED',
    'QUESTION_OPEN',
    'RESOLVED',
    'SUGGESTION_APPLIED',
    'SUGGESTION_DECLINED',
    'SUGGESTION_PENDING',
    'SUGGESTION_REVERTED',
    'SUGGESTION_SUPERSEDED',
    'THREAD_ITEM_TYPES',
    'Intent',
    'IntentKind',
    'ThreadItem',
    'ThreadItemType',
    'initial_item_state',
    'SUGGESTION_OP_TYPES',
]
