"""In-memory service builder — used across core + adapter tests."""
from __future__ import annotations

from dataclasses import dataclass

from anchor.core.clock import FixedClock
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore

from tests.fixtures.fakes import (
    FakeEmbedder,
    FakePdfExtractor,
    FakePdfRenderer,
    FakePolisher,
    FakeRegionExtractor,
)


@dataclass
class Services:
    workspace_store: MemoryWorkspaceStore
    doc_store: MemoryDocStore
    bus: MemoryEventBus
    workspace: WorkspaceService
    ingest: IngestService
    extractor: FakePdfExtractor
    renderer: FakePdfRenderer
    polisher: FakePolisher
    region_extractor: FakeRegionExtractor
    embedder: FakeEmbedder
    clock: FixedClock


def make_in_memory_services(*, page_count: int = 1) -> Services:
    workspace_store = MemoryWorkspaceStore()
    doc_store = MemoryDocStore()
    bus = MemoryEventBus()
    clock = FixedClock(ts=1700000000.0)
    extractor = FakePdfExtractor()
    renderer = FakePdfRenderer(page_count=page_count)
    polisher = FakePolisher()
    region_extractor = FakeRegionExtractor()
    embedder = FakeEmbedder()
    workspace = WorkspaceService(workspace_store, bus, clock=clock)
    ingest = IngestService(
        doc_store, bus,
        extractor=extractor, renderer=renderer,
        polisher=polisher, region_extractor=region_extractor,
        clock=clock,
    )
    return Services(
        workspace_store=workspace_store, doc_store=doc_store, bus=bus,
        workspace=workspace, ingest=ingest,
        extractor=extractor, renderer=renderer, polisher=polisher,
        region_extractor=region_extractor, embedder=embedder, clock=clock,
    )
