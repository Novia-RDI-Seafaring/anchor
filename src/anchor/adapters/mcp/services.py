"""MCP compatibility facade for project runtime construction.

The MCP adapter historically owned the per-project ``ServiceBundle`` builder.
It now delegates to ``anchor.adapters.project_runtime`` so MCP, CLI, and HTTP
can converge on one project runtime construction path without changing MCP
imports in a broad sweep.
"""

from __future__ import annotations

import importlib.util
import os
import sys

from anchor.adapters.project_runtime import (
    ProjectRuntime,
    build_ingest_service,
    build_project_runtime,
)
from anchor.core.ports.event_bus import EventBus
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.infra.config import AnchorConfig

ServiceBundle = ProjectRuntime


def fmu_tools_available() -> bool:
    """Cheap, side-effect-free probe matching anchor_fmus.build_service's gate.

    FMPy availability (or the ANCHOR_FMU_DEMO opt-in) is global, not per
    project, so the advertised tool list can decide it once without building a
    runtime or touching any project directory.
    """
    if os.environ.get("ANCHOR_FMU_DEMO") == "1":
        return True
    return importlib.util.find_spec("fmpy") is not None


async def active_extensions_for_bundle(bundle: ServiceBundle) -> set[str]:
    """Which extension capabilities currently have data in this project.

    Drives the tiered MCP surface (anchor#133): an extension's tools are
    advertised by default only when the resolved project actually has data for
    it. Best-effort and non-raising -- on any probe failure the extension is
    treated as inactive.
    """
    active: set[str] = set()
    if bundle.fmu is not None:
        try:
            if await bundle.fmu.list_models():
                active.add("fmu")
        except Exception:  # noqa: BLE001 -- probe must never break list_tools
            pass
    if bundle.cad is not None:
        try:
            if await bundle.cad.list_models():
                active.add("cad")
        except Exception:  # noqa: BLE001
            pass
    return active


def _warn_fmu_disabled(exc: Exception) -> None:
    print(f"Warning: anchor-mcp: FMU tools disabled - {exc}", file=sys.stderr)


def _build_ingest_service(
    config: AnchorConfig,
    bus: EventBus,
    doc_store: DocStore,
) -> IngestService:
    """Compatibility wrapper for MCP stdio wiring tests."""
    return build_ingest_service(config, bus, doc_store)


def build_bundle(config: AnchorConfig, *, base_url: str = "http://localhost:8002") -> ServiceBundle:
    """Wire every runtime module for one project from its resolved config."""
    return build_project_runtime(config, base_url=base_url, fmu_warning=_warn_fmu_disabled)
