"""
Active Document State Management

Manages the currently active document filter for RAG queries.
This module is separate from main.py to avoid circular dependencies.
"""

from typing import Optional

# Global state for active document ID
_active_document_id: Optional[str] = None


def get_active_document_id() -> Optional[str]:
    """Get the currently active document ID."""
    return _active_document_id


def set_active_document_id(document_id: Optional[str]) -> None:
    """Set the active document ID."""
    global _active_document_id
    _active_document_id = document_id if document_id != 'all' else None
