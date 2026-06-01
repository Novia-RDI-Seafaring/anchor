"""`anchor-mcp` stdio entrypoint."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from mcp.server.stdio import stdio_server

from anchor.adapters.mcp.server import build_mcp_server
from anchor.core.ports.event_bus import EventBus
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.config import AnchorConfig
from anchor.extensions.anchor_pdfs.infra.llm.openai_embedder import OpenAIEmbedder
from anchor.extensions.anchor_pdfs.infra.llm.openai_md_polisher import OpenAIPageMdPolisher
from anchor.extensions.anchor_pdfs.infra.llm.openai_region_extractor import OpenAIRegionExtractor
from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.infra.snapshot.headless_chromium_snapshotter import HeadlessChromiumSnapshotter
from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore


def _build_embedder(
    api_key: str | None,
    *,
    base_url: str | None = None,
    local_model: str = "BAAI/bge-small-en-v1.5",
):
    """Select the available semantic-search embedder for MCP document tools."""
    if api_key:
        return OpenAIEmbedder(api_key=api_key, base_url=base_url)
    try:
        from anchor.extensions.anchor_pdfs.infra.llm.local_sentence_transformer_embedder import (
            LocalSentenceTransformerEmbedder,
        )

        return LocalSentenceTransformerEmbedder(model=local_model)
    except ImportError:
        return None


def _build_ingest_service(config: AnchorConfig, bus: EventBus, doc_store: DocStore) -> IngestService:
    api_key = config.openai_api_key.get_secret_value() if config.openai_api_key else None
    has_openai = bool(api_key) or bool(os.environ.get("OPENAI_API_KEY"))
    openai_base_url = (config.openai_base_url or "").strip() or None
    embedder = _build_embedder(
        api_key if has_openai else None,
        base_url=openai_base_url,
        local_model=config.embed_model,
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


async def _run(data_dir: Path, base_url: str = "http://localhost:8002") -> None:
    config = AnchorConfig(data_dir=data_dir)
    bus = MemoryEventBus()
    workspace_store = FsWorkspaceStore(config.canvases_dir)
    doc_store = FsDocStore(config.data_dir)
    # The MCP server doesn't host the canvas itself — it loops through a
    # running `anchor serve` reachable at `base_url` for snapshot rendering.
    snapshotter = HeadlessChromiumSnapshotter(
        base_url=base_url, output_dir=config.data_dir / "snapshots",
    )
    workspace = WorkspaceService(workspace_store, bus, snapshotter=snapshotter)
    ingest = _build_ingest_service(config, bus, doc_store)

    # Wire CAD extension service so anchor-mcp exposes cad.* tools too.
    from anchor.extensions.anchor_cad import extension as cad_ext
    cad = cad_ext.build_service(data_dir, bus)

    # Wire FMU extension service. Real runtime needs FMPy; the synthetic
    # demo runtime is gated behind ANCHOR_FMU_DEMO=1. Without either,
    # the FMU tools are simply absent from this MCP server's tool list.
    # We log to stderr rather than swallowing so the user knows why.
    import sys
    fmu = None
    try:
        from anchor.extensions.anchor_fmus import extension as fmu_ext
        fmu = fmu_ext.build_service(data_dir, bus)
    except fmu_ext.FmuRuntimeUnavailableError as exc:
        print(f"Warning: anchor-mcp: FMU tools disabled - {exc}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: anchor-mcp: FMU tools failed to start - {exc}", file=sys.stderr)

    # Wire SysML extension — pure-Python, no optional deps to fall over.
    from anchor.extensions.anchor_sysml import extension as sysml_ext
    sysml = sysml_ext.build_service(data_dir, bus, workspace=workspace)

    # Wire synopsis service so MCP clients can compose entity-scoped PDFs/decks.
    from anchor.extensions.anchor_pdfs.core.services import SynopsisService
    from anchor.extensions.anchor_pdfs.infra.synopsis_renderers import (
        MarpSynopsisRenderer, PymupdfSynopsisRenderer,
    )
    synopsis = SynopsisService(
        doc_store,
        pdf_renderer=PymupdfSynopsisRenderer(),
        md_renderer=MarpSynopsisRenderer(),
    )

    server = build_mcp_server(
        workspace=workspace, ingest=ingest, doc_store=doc_store,
        fmu=fmu, cad=cad, sysml=sysml, synopsis=synopsis,
    )
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="Anchor v2 MCP (stdio)")
    parser.add_argument("--data-dir", "-d", default="./data")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8002",
        help="URL of the running `anchor serve` the snapshotter loops through.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    asyncio.run(_run(Path(args.data_dir), base_url=args.base_url))


if __name__ == "__main__":
    main()
