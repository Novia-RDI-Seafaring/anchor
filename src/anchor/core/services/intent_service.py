"""Anchor constructor compatibility for the independent thread service."""
from __future__ import annotations

from collections.abc import Callable

from anchor.core.ports.event_bus import EventBus
from anchor.core.ports.intent_store import IntentStore
from anchor.core.ports.thread_host import ThreadHost
from anchor.core.services.anchor_pending_signals import AnchorPendingSignals
from anchor.core.services.anchor_thread_host import AnchorThreadHost
from anchor.core.services.workspace_service import WorkspaceService
from intent_layer.errors import SuggestionApplyError as SuggestionApplyError
from intent_layer.errors import ThreadError as ThreadError
from intent_layer.service import PROJECT_SIGNAL_ID as PROJECT_SIGNAL_ID
from intent_layer.service import IntentService as ThreadService
from intent_layer.service import UnknownIntentKindError as UnknownIntentKindError


class IntentService(ThreadService):
    def __init__(self, store: IntentStore, bus: EventBus, *,
                 now: Callable[[], float] | None = None,
                 workspace: WorkspaceService | None = None,
                 host: ThreadHost | None = None) -> None:
        super().__init__(store, AnchorPendingSignals(bus), now=now,
                         host=host if host is not None else AnchorThreadHost(workspace))

__all__ = ["PROJECT_SIGNAL_ID", "IntentService", "SuggestionApplyError", "ThreadError", "UnknownIntentKindError"]
