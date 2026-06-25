"""Concrete service wiring used by the CLI commands."""

from __future__ import annotations

import os
from pathlib import Path


def _egress_settings(config) -> tuple[str | None, bool, str | None]:
    """Resolve (api_key, has_openai, base_url) honoring local-only / no-egress.

    In local-only mode no OpenAI client is ever built: ``has_openai`` is forced
    False (so polish + region extraction stay unwired) and the base_url is
    dropped, regardless of any key in the env. Embeddings stay local too — the
    embedder selection only goes remote for a ``text-embedding-*`` model, which
    local-only never configures. This is the runtime assertion that a
    confidential ingest performs no external egress. The HuggingFace offline env
    is pinned here so cached model weights load without reaching the network.
    """
    if config.local_only:
        from anchor.infra.models import enforce_offline

        enforce_offline()
        return None, False, None
    api_key = config.openai_api_key.get_secret_value() if config.openai_api_key else None
    # OpenAI SDK reads OPENAI_API_KEY from env by default; instantiate if either
    # path has a key so polish/region steps don't silently no-op.
    has_openai = bool(api_key) or bool(os.environ.get("OPENAI_API_KEY"))
    # base_url lets users point polish/region at an OpenAI-compatible backend
    # (Azure OpenAI, Ollama, vLLM, LM Studio). Empty string is treated the same
    # as None so a stray env var doesn't break stock OpenAI usage.
    openai_base_url = (config.openai_base_url or "").strip() or None
    return api_key, has_openai, openai_base_url


def _build_real_services(data_dir: Path, *, base_url: str = "http://localhost:8002"):
    """Wire concrete adapters. Polish/region-extract are OpenAI-only and become
    no-ops if the user hasn't provided ANCHOR_OPENAI_API_KEY, silver still
    builds, gold simply skips. Embeddings follow ANCHOR_EMBED_MODEL; the
    local default stays local even when an OpenAI key is present.

    `base_url` is where the wired SnapshotPort points headless chromium.
    Default matches `anchor serve --port 8002`; override when serving on a
    non-default port."""
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
    from anchor.infra.environment import config_for_data_dir
    from anchor.infra.snapshot.headless_chromium_snapshotter import (
        HeadlessChromiumSnapshotter,
    )
    from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore

    # Layer the environment config when data_dir is a project under an
    # environment; falls back to a plain config (with legacy anchor.toml
    # walk-up) for an explicit external dir.
    config = config_for_data_dir(data_dir)
    bus = MemoryEventBus()
    workspace_store = FsWorkspaceStore(config.canvases_dir)
    doc_store = FsDocStore(config.data_dir)
    snapshotter = HeadlessChromiumSnapshotter(
        base_url=base_url,
        output_dir=config.data_dir / "snapshots",
    )
    workspace = WorkspaceService(workspace_store, bus, snapshotter=snapshotter)
    api_key, has_openai, openai_base_url = _egress_settings(config)
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

    api_key, _has_openai, openai_base_url = _egress_settings(config)
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
    from anchor.infra.environment import config_for_data_dir

    config = config_for_data_dir(data_dir)
    bus = MemoryEventBus()
    doc_store = FsDocStore(config.data_dir)
    return config, _build_ingest_session_service(config, bus, doc_store)
