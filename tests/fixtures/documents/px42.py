"""Real PX-42 document runtime with a deterministic, non-semantic embedder."""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

from anchor.adapters.project_runtime import ProjectRuntime, RuntimeProfile
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.config import AnchorConfig
from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore

PDF = Path(__file__).with_name("synthetic-process-pump-datasheet.pdf")
SHA256 = "c9966c8f9b7ccef0e1cbdcf4fbc26b51014f7b627210180f8321546eac601f32"
SLUG = "px42"


class FixtureLexicalEmbedder:
    """Hashed token counts test retrieval plumbing, not model semantics."""

    model_id = "fixture-lexical-sha256-256-v1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * 256
            for token in re.findall(r"[a-z0-9]+", text.casefold()):
                index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big") % len(vector)
                vector[index] += 1
            norm = math.sqrt(sum(value * value for value in vector)) or 1
            vectors.append([value / norm for value in vector])
        return vectors


def build_px42_runtime(data_dir: Path) -> ProjectRuntime:
    """Use production extraction/stores/services, without a provider client."""
    config = AnchorConfig(_env_file=None, data_dir=data_dir, provider="local",
                          local_only=True, embed_model=FixtureLexicalEmbedder.model_id)
    bus = MemoryEventBus()
    store = FsDocStore(data_dir)
    workspace = WorkspaceService(FsWorkspaceStore(config.canvases_dir), bus)
    ingest = IngestService(store, bus, extractor=DoclingPdfExtractor(device="cpu"),
                           renderer=PymupdfPdfRenderer(), embedder=FixtureLexicalEmbedder(),
                           embed_model_id=FixtureLexicalEmbedder.model_id)
    return ProjectRuntime(RuntimeProfile.INGEST, config, bus, workspace, store, ingest)
