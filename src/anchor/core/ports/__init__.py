"""Canvas-core ports.

Only the *generic* canvas ports live here. Domain-specific ports (DocStore,
PdfExtractor, PageMdPolisher, RegionExtractor, Embedder, PdfRenderer) live
inside their owning extension under
`anchor.extensions.<ext>.core.ports.*` — that's how the canvas/extensions
split shows up at the import boundary.
"""
from anchor.core.ports.event_bus import EventBus
from anchor.core.ports.snapshot import SnapshotPort, SnapshotResult
from anchor.core.ports.workspace_store import WorkspaceStore

__all__ = ["WorkspaceStore", "EventBus", "SnapshotPort", "SnapshotResult"]
