"""Project-level runtime composition shared by transport adapters.

This module is the composition root for one project. It belongs to the adapter
layer because it wires core modules, infrastructure adapters, and bundled
extensions. Named profiles keep callers independent of the internal module
graph and prevent lightweight commands from starting unrelated runtimes.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anchor.adapters.extension_host import ExtensionRuntimeStatus
    from anchor.core.ports.event_bus import EventBus
    from anchor.core.services.intent_service import IntentService
    from anchor.core.services.workspace_service import WorkspaceService
    from anchor.extensions.anchor_cad.core.services import CadService
    from anchor.extensions.anchor_fmus.core.services import FmuService
    from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
    from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
    from anchor.extensions.anchor_pdfs.core.services import IngestService, SynopsisService
    from anchor.extensions.anchor_sysml.core.services import SysmlService
    from anchor.infra.config import AnchorConfig


class RuntimeProfile(StrEnum):
    """Supported project runtime shapes for adapter entry points."""

    CANVAS = "canvas"
    INGEST = "ingest"
    EXTENSIONS = "extensions"
    FULL = "full"


@dataclass(frozen=True, slots=True)
class _RuntimeFeatures:
    ingest: bool = False
    intents: bool = False
    ingest_session: bool = False
    extensions: bool = False
    synopsis: bool = False


_PROFILE_FEATURES = {
    RuntimeProfile.CANVAS: _RuntimeFeatures(),
    RuntimeProfile.INGEST: _RuntimeFeatures(ingest=True),
    RuntimeProfile.EXTENSIONS: _RuntimeFeatures(extensions=True),
    RuntimeProfile.FULL: _RuntimeFeatures(
        ingest=True,
        intents=True,
        ingest_session=True,
        extensions=True,
        synopsis=True,
    ),
}


@dataclass(slots=True)
class ProjectRuntime:
    """Runtime modules bound to one project's data directory."""

    profile: RuntimeProfile
    config: AnchorConfig
    bus: EventBus
    workspace: WorkspaceService
    doc_store: DocStore
    ingest: IngestService | None = None
    intents: IntentService | None = None
    ingest_session: IngestSessionService | None = None
    cad: CadService | None = None
    sysml: SysmlService | None = None
    synopsis: SynopsisService | None = None
    fmu: FmuService | None = None
    extension_status: dict[str, ExtensionRuntimeStatus] = field(default_factory=dict)

    def require_ingest(self) -> IngestService:
        """Return keyed PDF ingest or fail clearly for a reduced profile."""
        if self.ingest is None:
            raise RuntimeError(
                f"the {self.profile.value!r} runtime profile does not include PDF ingest"
            )
        return self.ingest


def egress_settings(config: AnchorConfig) -> tuple[str | None, bool, str | None]:
    """Resolve API key, client availability, and base URL for one project."""
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
    """Build the keyed PDF ingest module for one project."""
    from anchor.extensions.anchor_pdfs.core.services import IngestService
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
    """Build harness ingestion against an existing project document store."""
    from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
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
    profile: RuntimeProfile = RuntimeProfile.FULL,
    base_url: str = "http://localhost:8002",
    fmu_warning: Callable[[Exception], None] | None = None,
) -> ProjectRuntime:
    """Build one project runtime using a named, stable composition profile."""
    from anchor.core.services.workspace_service import WorkspaceService
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from anchor.infra.snapshot.headless_chromium_snapshotter import (
        HeadlessChromiumSnapshotter,
    )
    from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore
    from anchor.infra.workspace_locks import InProcessWorkspaceLocks

    profile = RuntimeProfile(profile)
    features = _PROFILE_FEATURES[profile]
    data_dir = config.data_dir
    bus = MemoryEventBus()
    doc_store = FsDocStore(data_dir)
    workspace = WorkspaceService(
        FsWorkspaceStore(config.canvases_dir),
        bus,
        locks=InProcessWorkspaceLocks(),
        snapshotter=HeadlessChromiumSnapshotter(
            base_url=base_url,
            output_dir=data_dir / "snapshots",
        ),
    )

    intents = None
    if features.intents:
        from anchor.core.clock import SystemClock
        from anchor.core.services.intent_service import IntentService
        from anchor.infra.stores.fs_intent_store import FsIntentStore

        intents = IntentService(FsIntentStore(data_dir), bus, now=SystemClock().now)

    ingest = build_ingest_service(config, bus, doc_store) if features.ingest else None
    ingest_session = (
        build_ingest_session_service(config, bus, doc_store)
        if features.ingest_session
        else None
    )

    cad = None
    sysml = None
    fmu = None
    extension_status = {}
    if features.extensions:
        from anchor.adapters.extension_host import ExtensionHost

        extensions = ExtensionHost(data_dir).start_bundled(
            bus=bus,
            workspace=workspace,
            fmu_warning=fmu_warning,
        )
        cad = extensions.cad
        sysml = extensions.sysml
        fmu = extensions.fmu
        extension_status = extensions.status

    synopsis = None
    if features.synopsis:
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
        profile=profile,
        config=config,
        bus=bus,
        workspace=workspace,
        doc_store=doc_store,
        ingest=ingest,
        intents=intents,
        ingest_session=ingest_session,
        cad=cad,
        sysml=sysml,
        synopsis=synopsis,
        fmu=fmu,
        extension_status=extension_status,
    )


def build_project_runtime_for_data_dir(
    data_dir: Path,
    *,
    profile: RuntimeProfile = RuntimeProfile.FULL,
    base_url: str = "http://localhost:8002",
    fmu_warning: Callable[[Exception], None] | None = None,
) -> ProjectRuntime:
    """Resolve project configuration and build its named runtime profile."""
    from anchor.infra.environment import config_for_data_dir

    return build_project_runtime(
        config_for_data_dir(data_dir),
        profile=profile,
        base_url=base_url,
        fmu_warning=fmu_warning,
    )
