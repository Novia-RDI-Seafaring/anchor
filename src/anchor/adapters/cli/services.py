"""Concrete service wiring used by the CLI commands."""

from __future__ import annotations

from pathlib import Path


def _build_real_services(data_dir: Path, *, base_url: str = "http://localhost:8002"):
    """Wire concrete adapters. Polish/region-extract are OpenAI-only and become
    no-ops if the user hasn't provided ANCHOR_OPENAI_API_KEY, silver still
    builds, gold simply skips. Embeddings follow ANCHOR_EMBED_MODEL; the
    local default stays local even when an OpenAI key is present.

    `base_url` is where the wired SnapshotPort points headless chromium.
    Default matches `anchor serve --port 8002`; override when serving on a
    non-default port."""
    import os

    from anchor.core.services.workspace_service import WorkspaceService
    from anchor.extensions.anchor_pdfs.core.services import IngestService
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.extensions.anchor_pdfs.infra.llm.openai_md_polisher import OpenAIPageMdPolisher
    from anchor.extensions.anchor_pdfs.infra.llm.openai_region_extractor import (
        OpenAIRegionExtractor,
    )
    from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
    from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from anchor.infra.config import AnchorConfig
    from anchor.infra.snapshot.headless_chromium_snapshotter import (
        HeadlessChromiumSnapshotter,
    )
    from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore

    config = AnchorConfig(data_dir=data_dir)
    bus = MemoryEventBus()
    workspace_store = FsWorkspaceStore(config.canvases_dir)
    doc_store = FsDocStore(config.data_dir)
    snapshotter = HeadlessChromiumSnapshotter(
        base_url=base_url,
        output_dir=config.data_dir / "snapshots",
    )
    workspace = WorkspaceService(workspace_store, bus, snapshotter=snapshotter)
    api_key = config.openai_api_key.get_secret_value() if config.openai_api_key else None
    # OpenAI SDK reads OPENAI_API_KEY from env by default; instantiate if either path
    # has a key so polish/region steps don't silently no-op.
    has_openai = bool(api_key) or bool(os.environ.get("OPENAI_API_KEY"))
    # base_url lets users point polish/region at an OpenAI-compatible
    # backend (Azure OpenAI, Ollama, vLLM, LM Studio). Empty string is
    # treated the same as None so a stray env var doesn't break stock
    # OpenAI usage.
    openai_base_url = (config.openai_base_url or "").strip() or None
    from anchor.extensions.anchor_pdfs.infra.llm.embedder_selection import build_embedder

    embedder = build_embedder(
        model=config.embed_model,
        api_key=api_key,
        base_url=openai_base_url,
    )
    ingest = IngestService(
        doc_store,
        bus,
        extractor=DoclingPdfExtractor(device=config.docling_device),
        renderer=PymupdfPdfRenderer(),
        polisher=OpenAIPageMdPolisher(api_key=api_key, base_url=openai_base_url)
        if has_openai
        else None,
        region_extractor=OpenAIRegionExtractor(api_key=api_key, base_url=openai_base_url)
        if has_openai
        else None,
        embedder=embedder,
        embed_model_id=getattr(embedder, "model_id", None),
        default_polish_model=config.polish_model,
        default_region_model=config.region_model,
        default_dpi=config.dpi,
    )
    return config, bus, workspace, ingest, doc_store


def _build_ingest_session_service(config, bus, doc_store):
    """Wire the harness ingest-session service against an existing doc store.

    No polisher / region extractor here on purpose: in harness mode the
    agent is the vision model. Embeddings stay local (or follow
    ANCHOR_EMBED_MODEL) exactly like the keyed pipeline."""
    from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
    from anchor.extensions.anchor_pdfs.infra.fs_session_store import FsIngestSessionStore
    from anchor.extensions.anchor_pdfs.infra.llm.embedder_selection import build_embedder
    from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
    from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer

    api_key = config.openai_api_key.get_secret_value() if config.openai_api_key else None
    openai_base_url = (config.openai_base_url or "").strip() or None
    embedder = build_embedder(
        model=config.embed_model, api_key=api_key, base_url=openai_base_url,
    )
    return IngestSessionService(
        doc_store,
        FsIngestSessionStore(config.data_dir),
        bus,
        extractor=DoclingPdfExtractor(device=config.docling_device),
        renderer=PymupdfPdfRenderer(),
        embedder=embedder,
        embed_model_id=getattr(embedder, "model_id", None),
        default_dpi=config.dpi,
    )


def _build_session_services(data_dir: Path):
    """Standalone wiring for the `anchor ingest-session` commands."""
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from anchor.infra.config import AnchorConfig

    config = AnchorConfig(data_dir=data_dir)
    bus = MemoryEventBus()
    doc_store = FsDocStore(config.data_dir)
    return config, _build_ingest_session_service(config, bus, doc_store)
