"""Project-level runtime composition for adapter entry points.

This module is the shared composition root for project-bound adapter runtimes.
It intentionally lives under ``anchor.adapters`` because it wires transport
adapters, infra implementations, and first-party extensions together. Moving it
under ``anchor.infra`` would violate the import contract that infra does not
depend on extensions.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anchor.core.ports.event_bus import EventBus
from anchor.core.services.intent_service import IntentService
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.config import AnchorConfig


@dataclass
class ProjectRuntime:
    """All runtime modules bound to one project's data directory."""

    config: AnchorConfig
    bus: EventBus
    workspace: WorkspaceService
    ingest: IngestService
    doc_store: DocStore
    intents: IntentService | None = None
    ingest_session: IngestSessionService | None = None
    cad: Any | None = None
    sysml: Any | None = None
    synopsis: Any | None = None
    fmu: Any | None = None


def egress_settings(config: AnchorConfig) -> tuple[str | None, bool, str | None]:
    """Resolve (api_key, has_openai, base_url) honoring local-only mode."""
    if config.local_only:
        from anchor.infra.models import enforce_offline

        enforce_offline()
        return None, False, None
    api_key = config.openai_api_key.get_secret_value() if config.openai_api_key else None
    has_openai = bool(api_key) or bool(os.environ.get("OPENAI_API_KEY"))
    openai_base_url = (config.openai_base_url or "").strip() or None
    return api_key, has_openai, openai_base_url


def build_ingest_service(
    config: AnchorConfig,
    bus: EventBus,
    doc_store: DocStore,
) -> IngestService:
    """Wire the keyed PDF ingest runtime for one project."""
    from anchor.extensions.anchor_pdfs.infra.llm.embedder_selection import build_embedder
    from anchor.extensions.anchor_pdfs.infra.llm.openai_md_polisher import OpenAIPageMdPolisher
    from anchor.extensions.anchor_pdfs.infra.llm.openai_region_extractor import (
        OpenAIRegionExtractor,
    )
    from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
    from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer

    api_key, has_openai, openai_base_url = egress_settings(config)
    embedder = build_embedder(
        model=config.embed_model,
        api_key=api_key,
        base_url=openai_base_url,
    )
    return IngestService(
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


def build_ingest_session_service(
    config: AnchorConfig,
    bus: EventBus,
    doc_store: DocStore,
) -> IngestSessionService:
    """Wire harness ingest sessions against an existing document store."""
    from anchor.extensions.anchor_pdfs.infra.fs_session_store import FsIngestSessionStore
    from anchor.extensions.anchor_pdfs.infra.llm.embedder_selection import build_embedder
    from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
    from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer

    api_key, _has_openai, openai_base_url = egress_settings(config)
    embedder = build_embedder(
        model=config.embed_model,
        api_key=api_key,
        base_url=openai_base_url,
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


def build_project_runtime(
    config: AnchorConfig,
    *,
    base_url: str = "http://localhost:8002",
    include_intents: bool = True,
    include_ingest_session: bool = True,
    include_extensions: bool = True,
    include_synopsis: bool = True,
    fmu_warning: Callable[[Exception], None] | None = None,
) -> ProjectRuntime:
    """Wire every runtime module for one resolved project config."""
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.infra.snapshot.headless_chromium_snapshotter import (
        HeadlessChromiumSnapshotter,
    )
    from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore

    data_dir = config.data_dir
    bus = MemoryEventBus()
    workspace_store = FsWorkspaceStore(config.canvases_dir)
    doc_store = FsDocStore(data_dir)
    intents = None
    if include_intents:
        from anchor.core.clock import SystemClock
        from anchor.infra.stores.fs_intent_store import FsIntentStore

        intents = IntentService(FsIntentStore(data_dir), bus, now=SystemClock().now)
    snapshotter = HeadlessChromiumSnapshotter(
        base_url=base_url,
        output_dir=data_dir / "snapshots",
    )
    workspace = WorkspaceService(workspace_store, bus, snapshotter=snapshotter)
    ingest = build_ingest_service(config, bus, doc_store)
    ingest_session = (
        build_ingest_session_service(config, bus, doc_store)
        if include_ingest_session
        else None
    )

    cad = None
    sysml = None
    fmu = None
    if include_extensions:
        from anchor.extensions.anchor_cad import extension as cad_ext

        cad = cad_ext.build_service(data_dir, bus)

        try:
            from anchor.extensions.anchor_fmus import extension as fmu_ext

            fmu = fmu_ext.build_service(data_dir, bus)
        except Exception as exc:  # noqa: BLE001 - optional extension
            if fmu_warning is None:
                print(f"Warning: FMU extension disabled: {exc}", file=sys.stderr)
            else:
                fmu_warning(exc)

        from anchor.extensions.anchor_sysml import extension as sysml_ext

        sysml = sysml_ext.build_service(data_dir, bus, workspace=workspace)

    synopsis = None
    if include_synopsis:
        from anchor.extensions.anchor_pdfs.core.services import SynopsisService
        from anchor.extensions.anchor_pdfs.infra.synopsis_renderers import (
            MarpSynopsisRenderer,
            PymupdfSynopsisRenderer,
        )

        synopsis = SynopsisService(
            doc_store,
            pdf_renderer=PymupdfSynopsisRenderer(),
            md_renderer=MarpSynopsisRenderer(),
        )

    return ProjectRuntime(
        config=config,
        bus=bus,
        workspace=workspace,
        ingest=ingest,
        doc_store=doc_store,
        intents=intents,
        ingest_session=ingest_session,
        cad=cad,
        sysml=sysml,
        synopsis=synopsis,
        fmu=fmu,
    )


def build_project_runtime_for_data_dir(
    data_dir: Path,
    *,
    base_url: str = "http://localhost:8002",
    include_intents: bool = True,
    include_ingest_session: bool = True,
    include_extensions: bool = True,
    include_synopsis: bool = True,
    fmu_warning: Callable[[Exception], None] | None = None,
) -> ProjectRuntime:
    """Resolve config for ``data_dir`` and build its project runtime."""
    from anchor.infra.environment import config_for_data_dir

    return build_project_runtime(
        config_for_data_dir(data_dir),
        base_url=base_url,
        include_intents=include_intents,
        include_ingest_session=include_ingest_session,
        include_extensions=include_extensions,
        include_synopsis=include_synopsis,
        fmu_warning=fmu_warning,
    )
