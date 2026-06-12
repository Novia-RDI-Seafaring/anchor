"""Runtime status summary shared by HTTP and MCP adapters."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.infra.config import AnchorConfig, discover_config_file

logger = logging.getLogger(__name__)


async def build_status_summary(
    *,
    config: AnchorConfig,
    workspace: WorkspaceService,
    doc_store: DocStore,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Return the active project and data-zone summary.

    This is intentionally a diagnostic payload, not a readiness probe. It helps
    users confirm that an agent-launched MCP server resolved the same project
    folder and data directory that the browser or CLI is using.
    """
    resolved_config = config_path if config_path is not None else discover_config_file()
    workspaces, workspace_error = await _safe_list_workspaces(workspace)
    documents, document_error = await _safe_list_documents(doc_store)
    embeddings, embedding_error = await _safe_list_embeddings(doc_store)

    return {
        "process": {
            "cwd": str(Path.cwd()),
        },
        "config": {
            "path": str(resolved_config) if resolved_config is not None else None,
            "found": resolved_config is not None,
            "source": _config_source(resolved_config),
        },
        "data_dir": {
            "path": str(config.data_dir),
            "exists": config.data_dir.exists(),
        },
        "directories": {
            "bronze": _dir_status(config.bronze_dir),
            "silver": _dir_status(config.silver_dir),
            "gold": _dir_status(config.gold_dir),
            "canvases": _dir_status(config.canvases_dir),
        },
        "counts": {
            "workspaces": len(workspaces),
            "documents": len(documents),
            "embeddings": len(embeddings),
        },
        "errors": {
            "workspaces": workspace_error,
            "documents": document_error,
            "embeddings": embedding_error,
        },
        "provider": {
            "name": config.provider,
            # Harness mode is honest about how gold happens: the agent
            # performs polish + regions through ingest sessions; no key,
            # no Anchor-side vision endpoint.
            "harness_mode": (config.provider or "").lower() == "harness",
            "key_required": (config.provider or "").lower()
            not in ("local", "ollama", "harness", ""),
            "openai_base_url": config.openai_base_url or "api.openai.com",
            "embed_model": config.embed_model,
            "polish_model": config.polish_model,
            "region_model": config.region_model,
        },
        "api_keys": {
            "anchor_openai_api_key": config.openai_api_key is not None,
            "openai_api_key": bool(os.environ.get("OPENAI_API_KEY")),
        },
        "ingest_sessions": _ingest_session_counts(config.data_dir),
    }


async def _safe_list_workspaces(
    workspace: WorkspaceService,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        return await workspace.list_workspaces(), None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list workspaces for status summary.")
        return [], "Unable to list workspaces"


async def _safe_list_documents(doc_store: DocStore) -> tuple[list[dict[str, Any]], str | None]:
    try:
        return await doc_store.list_documents(), None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list documents for status summary.")
        return [], "Unable to list documents"


async def _safe_list_embeddings(doc_store: DocStore) -> tuple[list[dict[str, Any]], str | None]:
    try:
        return await doc_store.list_embeddings(), None
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to list embeddings for status summary.")
        return [], "Unable to list embeddings"


def _ingest_session_counts(data_dir: Path) -> dict[str, Any]:
    """Harness ingest sessions by state, plus the open ones (resume surface)."""
    import json

    staging = data_dir / "staging" / "ingest"
    counts: dict[str, int] = {}
    open_sessions: list[dict[str, Any]] = []
    if staging.is_dir():
        for session_file in sorted(staging.glob("*/session.json")):
            try:
                session = json.loads(session_file.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            state = str(session.get("state", "unknown"))
            counts[state] = counts.get(state, 0) + 1
            if state in ("open", "finalizing"):
                pages = session.get("pages") or {}
                open_sessions.append({
                    "session_id": session.get("session_id", session_file.parent.name),
                    "slug": session.get("slug"),
                    "state": state,
                    "page_count": session.get("page_count", len(pages)),
                    "submitted_pages": sum(
                        1 for info in pages.values()
                        if info.get("status") == "submitted"
                    ),
                })
    return {"counts": counts, "open": open_sessions}


def _dir_status(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
    }


def _config_source(config_path: Path | None) -> str:
    if os.environ.get("ANCHOR_CONFIG"):
        return "ANCHOR_CONFIG"
    if config_path is not None:
        return "cwd-search"
    return "environment-or-defaults"
