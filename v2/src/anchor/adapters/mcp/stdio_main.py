"""`anchor-mcp` stdio entrypoint."""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from mcp.server.stdio import stdio_server

from anchor.adapters.mcp.server import build_mcp_server
from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.core.services.workspace_service import WorkspaceService
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.config import AnchorConfig
from anchor.extensions.anchor_pdfs.infra.llm.openai_embedder import OpenAIEmbedder  # noqa: F401  (available)
from anchor.extensions.anchor_pdfs.infra.llm.openai_md_polisher import OpenAIPageMdPolisher
from anchor.extensions.anchor_pdfs.infra.llm.openai_region_extractor import OpenAIRegionExtractor
from anchor.extensions.anchor_pdfs.infra.pdf.docling_extractor import DoclingPdfExtractor
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore


async def _run(data_dir: Path) -> None:
    import os

    config = AnchorConfig(data_dir=data_dir)
    bus = MemoryEventBus()
    workspace_store = FsWorkspaceStore(config.canvases_dir)
    doc_store = FsDocStore(config.data_dir)
    workspace = WorkspaceService(workspace_store, bus)
    api_key = config.openai_api_key.get_secret_value() if config.openai_api_key else None
    has_openai = bool(api_key) or bool(os.environ.get("OPENAI_API_KEY"))
    ingest = IngestService(
        doc_store, bus,
        extractor=DoclingPdfExtractor(),
        renderer=PymupdfPdfRenderer(),
        polisher=OpenAIPageMdPolisher(api_key=api_key) if has_openai else None,
        region_extractor=OpenAIRegionExtractor(api_key=api_key) if has_openai else None,
    )

    # Wire CAD extension service so anchor-mcp exposes cad.* tools too.
    from anchor.extensions.anchor_cad import extension as cad_ext
    cad = cad_ext.build_service(data_dir, bus)

    # Wire FMU extension service if FmuService is importable. Falls back
    # silently to no-FMU if FMPy or its deps aren't installed.
    fmu = None
    try:
        from anchor.extensions.anchor_fmus import extension as fmu_ext
        fmu = fmu_ext.build_service(data_dir, bus)
    except Exception:  # noqa: BLE001
        pass

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
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    asyncio.run(_run(Path(args.data_dir)))


if __name__ == "__main__":
    main()
