"""Concrete runtime wiring used by CLI commands."""

from __future__ import annotations

from pathlib import Path


def _egress_settings(config) -> tuple[str | None, bool, str | None]:
    """Compatibility wrapper for CLI tests and private call sites."""
    from anchor.adapters.project_runtime import egress_settings

    return egress_settings(config)


def _build_real_services(data_dir: Path, *, base_url: str = "http://localhost:8002"):
    """Wire the base project runtime used by ordinary CLI commands.

    The return shape is intentionally unchanged:
    ``(config, bus, workspace, ingest, doc_store)``.

    Ordinary CLI commands historically did not build optional extensions,
    intents, synopsis, or harness ingest sessions. Keep those off here so
    machine-readable CLI output does not gain optional startup warnings or
    unrelated side effects.
    """
    from anchor.adapters.project_runtime import build_project_runtime_for_data_dir

    runtime = build_project_runtime_for_data_dir(
        data_dir,
        base_url=base_url,
        include_intents=False,
        include_ingest_session=False,
        include_extensions=False,
        include_synopsis=False,
    )
    return (
        runtime.config,
        runtime.bus,
        runtime.workspace,
        runtime.require_ingest(),
        runtime.doc_store,
    )


def _build_canvas_runtime(data_dir: Path, *, base_url: str = "http://localhost:8002"):
    """Wire canvas commands without initializing PDF ingest or extensions."""
    from anchor.adapters.project_runtime import build_project_runtime_for_data_dir

    return build_project_runtime_for_data_dir(
        data_dir,
        base_url=base_url,
        include_ingest=False,
        include_intents=False,
        include_ingest_session=False,
        include_extensions=False,
        include_synopsis=False,
    )


def _build_ingest_session_service(config, bus, doc_store):
    """Wire the harness ingest-session runtime against an existing doc store."""
    from anchor.adapters.project_runtime import build_ingest_session_service

    return build_ingest_session_service(config, bus, doc_store)


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
