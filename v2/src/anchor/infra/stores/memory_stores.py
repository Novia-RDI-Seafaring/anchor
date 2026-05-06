"""In-memory canvas store implementations.

Only contains canvas-primitive stores. PDF-specific MemoryDocStore lives
at `anchor.extensions.anchor_pdfs.infra.memory_doc_store` — that's how
the canvas/extensions split shows up at the import boundary.
"""
from anchor.infra.stores.memory_workspace_store import MemoryWorkspaceStore

__all__ = ["MemoryWorkspaceStore"]
