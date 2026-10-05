"""Compatibility helpers for CLI project runtime construction."""

from __future__ import annotations

from pathlib import Path


def _build_real_services(data_dir: Path, *, base_url: str = "http://localhost:8002"):
    """Return the historical tuple backed by the ingest runtime profile."""
    from anchor.adapters.project_runtime import (
        RuntimeProfile,
        build_project_runtime_for_data_dir,
    )

    runtime = build_project_runtime_for_data_dir(
        data_dir,
        profile=RuntimeProfile.INGEST,
        base_url=base_url,
    )
    return (
        runtime.config,
        runtime.bus,
        runtime.workspace,
        runtime.require_ingest(),
        runtime.doc_store,
    )


def _build_canvas_runtime(data_dir: Path, *, base_url: str = "http://localhost:8002"):
    """Build canvas storage without PDF models or bundled extensions."""
    from anchor.adapters.project_runtime import (
        RuntimeProfile,
        build_project_runtime_for_data_dir,
    )

    return build_project_runtime_for_data_dir(
        data_dir,
        profile=RuntimeProfile.CANVAS,
        base_url=base_url,
    )


def _build_session_services(data_dir: Path):
    """Standalone wiring for the `anchor ingest-session` commands."""
    from anchor.adapters.project_runtime import build_ingest_session_service
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.infra.bus.memory_bus import MemoryEventBus
    from anchor.infra.environment import config_for_data_dir

    config = config_for_data_dir(data_dir)
    bus = MemoryEventBus()
    doc_store = FsDocStore(config.data_dir)
    return config, build_ingest_session_service(config, bus, doc_store)
