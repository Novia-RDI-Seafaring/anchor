"""
Request Context Management

Manages request-scoped context including model selection and active document filtering.
Uses ContextVars for thread-safe request isolation.
"""

from contextvars import ContextVar
from typing import Optional

# Context variable to store the model ID for the current request
model_id_ctx: ContextVar[Optional[str]] = ContextVar("model_id", default=None)

# Global state for active document ID (not request-scoped, shared across requests)
_active_document_id: Optional[str] = None


def get_current_model_id() -> Optional[str]:
    """Get the model ID for the current request."""
    return model_id_ctx.get()


def set_current_model_id(model_id: str) -> None:
    """Set the model ID for the current request."""
    model_id_ctx.set(model_id)


def get_active_document_id() -> Optional[str]:
    """Get the currently active document ID for RAG filtering."""
    return _active_document_id


def set_active_document_id(document_id: Optional[str]) -> None:
    """Set the active document ID for RAG filtering."""
    global _active_document_id
    if isinstance(document_id, str):
        normalized = document_id.strip()
        _active_document_id = normalized or None
        return
    _active_document_id = document_id
