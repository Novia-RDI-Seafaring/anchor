"""`anchor-mcp` stdio entrypoint."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from mcp.server.stdio import stdio_server

from anchor.adapters.mcp.router import ProjectRouter
from anchor.adapters.mcp.server import build_mcp_server
from anchor.adapters.mcp.services import build_bundle
from anchor.core.ports.event_bus import EventBus
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ingest.session import IngestSessionService
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.infra.fs_session_store import FsIngestSessionStore
from anchor.extensions.anchor_pdfs.infra.llm.embedder_selection import build_embedder
from anchor.extensions.anchor_pdfs.infra.llm.openai_md_polisher import OpenAIPageMdPolisher
from anchor.extensions.anchor_pdfs.infra.llm.openai_region_extractor import OpenAIRegionExtractor
from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
from anchor.infra.config import AnchorConfig


def _build_ingest_service(config: AnchorConfig, bus: EventBus, doc_store: DocStore) -> IngestService:
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


def _config_for_data_dir(data_dir: Path | None) -> AnchorConfig:
    """Use an explicit MCP flag when present, otherwise defer to AnchorConfig."""
    if data_dir is not None:
        return AnchorConfig(data_dir=data_dir)
    return AnchorConfig()


def _apply_project(project: Path | None) -> None:
    """Point config resolution at an `anchor init` folder.

    Any agent can use a project's Anchor by naming the folder — no per-project
    reinstall. ``--project`` sets ANCHOR_CONFIG so the whole config (data dir,
    models, data zone) resolves from that folder's anchor.toml, even when the
    server's working directory is elsewhere. A bare ``anchor-mcp`` launched
    inside the folder already resolves it via walk-up; this is the explicit
    handle for when it isn't.
    """
    if project is None:
        return
    import sys

    config_file = project.expanduser() / "anchor.toml"
    if config_file.is_file():
        os.environ["ANCHOR_CONFIG"] = str(config_file)
    else:
        print(
            f"Warning: anchor-mcp: no anchor.toml in {project} — run `anchor init` there. "
            "Falling back to environment / defaults.",
            file=sys.stderr,
        )


async def _run(
    *,
    env: Path | None = None,
    data_dir: Path | None = None,
    base_url: str = "http://localhost:8002",
) -> None:
    """Serve MCP over stdio.

    With ``env`` set, run the #120 multiproject model: one server for that
    environment, projects addressed by per-call name, lifecycle tools, and
    self-correcting resolution errors. Otherwise serve a single project bound
    to the resolved ``data_dir`` (legacy ``--project`` / ``--data-dir``).
    """
    if env is not None:
        router = ProjectRouter(env_arg=env, base_url=base_url)
        server = build_mcp_server(router=router)
    else:
        config = _config_for_data_dir(data_dir)
        bundle = build_bundle(config, base_url=base_url)
        server = build_mcp_server(bundle=bundle)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="Anchor v2 MCP (stdio)")
    parser.add_argument(
        "--env",
        type=Path,
        default=None,
        help="An Anchor environment dir (anchor.toml + projects/). Serves every "
        "project in it; name the project per call. The #120 multiproject model.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Legacy single-project mode: an `anchor init` folder whose anchor.toml "
        "(data dir, models, zone) binds the whole server. Ignored when --env is set.",
    )
    parser.add_argument(
        "--data-dir",
        "-d",
        type=Path,
        default=None,
        help="Legacy single-project storage root. Defaults to the resolved config "
        "(--project / anchor.toml / ANCHOR_DATA_DIR), else ~/anchor-data.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8002",
        help="URL of the running `anchor serve` the snapshotter loops through.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    if args.env is None:
        _apply_project(args.project)
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    asyncio.run(_run(env=args.env, data_dir=args.data_dir, base_url=args.base_url))


if __name__ == "__main__":
    main()
