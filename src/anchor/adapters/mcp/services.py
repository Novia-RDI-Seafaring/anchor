"""Per-project service bundle for the MCP server (anchor#120).

A :class:`ServiceBundle` is everything a project needs to answer tool calls:
its workspace/ingest/doc services plus the optional CAD/FMU/SysML/synopsis
extensions, all wired against one project's ``data_dir``. The multiproject
router builds one bundle per project (cached), so a single MCP server serves
any number of projects without rebinding at startup. Legacy single-project
mode builds exactly one bundle.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from typing import Any

from anchor.core.ports.event_bus import EventBus
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.config import AnchorConfig


@dataclass
class ServiceBundle:
    """All services bound to one project's data directory."""

    config: AnchorConfig
    bus: EventBus
    workspace: WorkspaceService
    ingest: IngestService
    doc_store: DocStore
    ingest_session: IngestSessionService | None = None
    cad: Any | None = None
    sysml: Any | None = None
    synopsis: Any | None = None
    fmu: Any | None = None


def fmu_tools_available() -> bool:
    """Cheap, side-effect-free probe matching anchor_fmus.build_service's gate.

    FMPy availability (or the ANCHOR_FMU_DEMO opt-in) is global, not per
    project, so the advertised tool list can decide it once without building a
    service or touching any project directory.
    """
    if os.environ.get("ANCHOR_FMU_DEMO") == "1":
        return True
    return importlib.util.find_spec("fmpy") is not None


def _build_ingest_service(config: AnchorConfig, bus: EventBus, doc_store: DocStore) -> IngestService:
    from anchor.extensions.anchor_pdfs.infra.llm.embedder_selection import build_embedder
    from anchor.extensions.anchor_pdfs.infra.llm.openai_md_polisher import OpenAIPageMdPolisher
    from anchor.extensions.anchor_pdfs.infra.llm.openai_region_extractor import (
        OpenAIRegionExtractor,
    )
    from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
    from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer

    api_key = config.openai_api_key.get_secret_value() if config.openai_api_key else None
    has_openai = bool(api_key) or bool(os.environ.get("OPENAI_API_KEY"))
    openai_base_url = (config.openai_base_url or "").strip() or None
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


def _build_ingest_session_service(
    config: AnchorConfig, bus: EventBus, doc_store: DocStore,
) -> IngestSessionService:
    """Harness ingest sessions: the agent polishes pages + groups regions;
    this service runs the mechanical half against the same doc store."""
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


def build_bundle(config: AnchorConfig, *, base_url: str = "http://localhost:8002") -> ServiceBundle:
    """Wire every service for one project from its resolved ``config``."""
    from anchor.extensions.anchor_pdfs.core.services import SynopsisService
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.extensions.anchor_pdfs.infra.synopsis_renderers import (
        MarpSynopsisRenderer,
        PymupdfSynopsisRenderer,
    )
    from anchor.infra.snapshot.headless_chromium_snapshotter import HeadlessChromiumSnapshotter
    from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore

    data_dir = config.data_dir
    bus = MemoryEventBus()
    workspace_store = FsWorkspaceStore(config.canvases_dir)
    doc_store = FsDocStore(data_dir)
    snapshotter = HeadlessChromiumSnapshotter(
        base_url=base_url, output_dir=data_dir / "snapshots",
    )
    workspace = WorkspaceService(workspace_store, bus, snapshotter=snapshotter)
    ingest = _build_ingest_service(config, bus, doc_store)
    ingest_session = _build_ingest_session_service(config, bus, doc_store)

    from anchor.extensions.anchor_cad import extension as cad_ext

    cad = cad_ext.build_service(data_dir, bus)

    fmu = None
    try:
        from anchor.extensions.anchor_fmus import extension as fmu_ext

        fmu = fmu_ext.build_service(data_dir, bus)
    except Exception as exc:  # noqa: BLE001 — FMU is optional; log, don't fail the bundle
        print(f"Warning: anchor-mcp: FMU tools disabled - {exc}", file=sys.stderr)

    from anchor.extensions.anchor_sysml import extension as sysml_ext

    sysml = sysml_ext.build_service(data_dir, bus, workspace=workspace)

    synopsis = SynopsisService(
        doc_store,
        pdf_renderer=PymupdfSynopsisRenderer(),
        md_renderer=MarpSynopsisRenderer(),
    )

    return ServiceBundle(
        config=config,
        bus=bus,
        workspace=workspace,
        ingest=ingest,
        doc_store=doc_store,
        ingest_session=ingest_session,
        cad=cad,
        sysml=sysml,
        synopsis=synopsis,
        fmu=fmu,
    )
