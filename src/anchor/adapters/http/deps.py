"""FastAPI dependency providers — pull services from app.state."""
from __future__ import annotations

from fastapi import Request

from anchor.core.events.actor import Actor, set_current_actor
from anchor.core.ports.event_bus import EventBus
from anchor.core.services.intent_service import IntentService
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService


def get_workspace_service(request: Request) -> WorkspaceService:
    return request.app.state.workspace_service


def get_ingest_service(request: Request) -> IngestService:
    return request.app.state.ingest_service


def get_doc_store(request: Request) -> DocStore:
    return request.app.state.doc_store


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.bus


def get_intent_service(request: Request) -> IntentService:
    return request.app.state.intent_service


def apply_actor_override(actor: Actor | None) -> None:
    """Replace the middleware's human/browser default with the request
    body's explicit ``actor`` (#322). No reset needed: the contextvar
    lives in this request's context only, and the middleware's scope-exit
    restores the outer state."""
    if actor is not None:
        set_current_actor(actor)
