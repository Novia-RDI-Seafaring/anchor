"""MCP helpers for shared project runtime construction."""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import TYPE_CHECKING

from anchor.adapters.project_runtime import ProjectRuntime

if TYPE_CHECKING:
    from anchor.core.ports.event_bus import EventBus
    from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
    from anchor.extensions.anchor_pdfs.core.services import IngestService
    from anchor.infra.config import AnchorConfig

def fmu_tools_available() -> bool:
    """Report whether the optional real or explicitly synthetic FMU runtime exists."""
    if os.environ.get("ANCHOR_FMU_DEMO") == "1":
        return True
    return importlib.util.find_spec("fmpy") is not None


async def active_extensions_for_bundle(bundle: ProjectRuntime) -> set[str]:
    """Return data-bearing extension capabilities active in one project.

    FMU and CAD count uploaded models; SysML has no model store, so its
    per-project data is ``sysml:*`` nodes on canvases.
    """
    active: set[str] = set()
    if bundle.fmu is not None:
        try:
            if await bundle.fmu.list_models():
                active.add("fmu")
        except Exception:  # noqa: BLE001 - discovery must not break list_tools
            pass
    if bundle.cad is not None:
        try:
            if await bundle.cad.list_models():
                active.add("cad")
        except Exception:  # noqa: BLE001 - discovery must not break list_tools
            pass
    if bundle.sysml is not None:
        try:
            if await _project_has_sysml_nodes(bundle):
                active.add("sysml")
        except Exception:  # noqa: BLE001 - discovery must not break list_tools
            pass
    return active


async def _project_has_sysml_nodes(bundle: ProjectRuntime) -> bool:
    for meta in await bundle.workspace.list_workspaces():
        state = await bundle.workspace.get_state(meta["slug"])
        if any(
            str(node.get("node_type", "")).startswith("sysml:")
            for node in state.get("nodes", [])
        ):
            return True
    return False


def _warn_fmu_disabled(exc: Exception) -> None:
    print(f"Warning: anchor-mcp: FMU tools disabled - {exc}", file=sys.stderr)


def _build_ingest_service(
    config: AnchorConfig,
    bus: EventBus,
    doc_store: DocStore,
) -> IngestService:
    """Keep the existing private MCP interface over shared ingest wiring."""
    from anchor.adapters.project_runtime import build_ingest_service

    return build_ingest_service(config, bus, doc_store)


def build_bundle(
    config: AnchorConfig,
    *,
    base_url: str = "http://localhost:8002",
) -> ProjectRuntime:
    """Build the full project runtime used by MCP tool dispatch."""
    from anchor.adapters.project_runtime import RuntimeProfile, build_project_runtime

    return build_project_runtime(
        config,
        profile=RuntimeProfile.FULL,
        base_url=base_url,
        fmu_warning=_warn_fmu_disabled,
    )
