"""Ingestion pipeline — orchestrates bronze → silver → gold for a single PDF.

Two entry points:

- `run_silver_pipeline` — deterministic only (no LLM), called on upload.
- `run_full_pipeline` — silver + LLM polish + gold regions, called on demand.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return s or "doc"


def run_silver_pipeline(
    pdf_path: Path,
    data_dir: Path,
    *,
    slug: str | None = None,
    dpi: int = 150,
) -> Path:
    """Run the deterministic silver pipeline for a PDF.

    Creates `data_dir/silver/<slug>/` with:
        docling.json, index.json, pages.meta.json, pages/N.png, pages/N.raw.md, pages/N.md

    The `.md` files are copies of `.raw.md` (no polish) — the LLM polish stage
    is run separately.

    Reuses KETJU's cached docling output if found next to the PDF
    (`<file>.pdf.docling.json`), avoiding a second docling run.

    Returns the silver directory path.
    """
    from .silver import build_index, build_pages_meta, render_pages_md, render_pages_png

    slug = slug or _slugify(pdf_path.stem)
    silver_dir = data_dir / "silver" / slug
    pages_dir = silver_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # 1. Docling extraction (skip if already done)
    docling_path = silver_dir / "docling.json"
    if not docling_path.exists():
        from .bronze import pdf_to_silver
        logger.info("pipeline: running docling for %s", pdf_path.name)
        pdf_to_silver(pdf_path, silver_dir)
    docling = json.loads(docling_path.read_text())

    # 2. Index + pages.meta
    index = build_index(docling, filename=pdf_path.name, title=pdf_path.stem)
    (silver_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    meta = build_pages_meta(docling)
    (silver_dir / "pages.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 3. Page PNGs
    needed_pages = sorted({
        int(it["page"])
        for it in docling.get("items", [])
        if isinstance(it, dict) and isinstance(it.get("page"), (int, float))
    })
    missing = [pg for pg in needed_pages if not (pages_dir / f"{pg}.png").exists()]
    if missing:
        logger.info("pipeline: rendering %d page PNGs @ %d dpi", len(needed_pages), dpi)
        render_pages_png(pdf_path, pages_dir, dpi=dpi)

    # 4. Raw md seeds (and copy as .md — polishing is a separate step)
    seed = render_pages_md(docling)
    for pg, md in seed.items():
        (pages_dir / f"{pg}.raw.md").write_text(md, encoding="utf-8")
        md_path = pages_dir / f"{pg}.md"
        if not md_path.exists():
            md_path.write_text(md, encoding="utf-8")

    logger.info("pipeline: silver done for %s (%d pages)", slug, len(seed))
    return silver_dir


ProgressCallback = None  # type alias defined below
from typing import Callable, Optional
ProgressCallback = Optional[Callable[[str, int, int], None]]
"""(stage, current_page, total_pages) — called as each page completes."""


def run_full_pipeline(
    pdf_path: Path,
    data_dir: Path,
    *,
    slug: str | None = None,
    dpi: int = 150,
    polish: bool = True,
    regions: bool = True,
    model: str = "gpt-5.4",
    on_progress: ProgressCallback = None,
) -> dict:
    """Run the full pipeline: silver (deterministic) + LLM polish + gold regions.

    Returns a summary dict with counts for each stage.
    """
    from .gold import extract_page_regions
    from .silver import needs_polish, polish_pages_md, render_pages_md

    slug = slug or _slugify(pdf_path.stem)
    silver_dir = run_silver_pipeline(pdf_path, data_dir, slug=slug, dpi=dpi)
    pages_dir = silver_dir / "pages"

    docling = json.loads((silver_dir / "docling.json").read_text())
    needed_pages = sorted({
        int(it["page"])
        for it in docling.get("items", [])
        if isinstance(it, dict) and isinstance(it.get("page"), (int, float))
    })

    total = len(needed_pages)
    result: dict = {
        "slug": slug,
        "pages": total,
        "polished": 0,
        "regions": 0,
    }

    # LLM polish
    if polish:
        from .openai_clients import OpenAIPageMdPolisher

        if on_progress:
            on_progress("polishing", 0, total)

        seed = render_pages_md(docling)
        polisher = OpenAIPageMdPolisher()
        polished = polish_pages_md(
            docling,
            pages_png_dir=pages_dir,
            deterministic_md=seed,
            client=polisher,
            model=model,
        )
        for i, (pg, md) in enumerate(polished.items()):
            (pages_dir / f"{pg}.md").write_text(md, encoding="utf-8")
            if on_progress:
                on_progress("polishing", i + 1, total)
        result["polished"] = sum(1 for pg in needed_pages if needs_polish(docling, pg))
        logger.info("pipeline: polished %d pages for %s", result["polished"], slug)

    # Gold regions
    if regions:
        from .openai_clients import OpenAIRegionExtractor

        if on_progress:
            on_progress("regions", 0, total)

        gold_pages_dir = data_dir / "gold" / slug / "pages"
        gold_pages_dir.mkdir(parents=True, exist_ok=True)
        extractor = OpenAIRegionExtractor()
        region_count = 0

        for i, pg in enumerate(needed_pages):
            out_json = gold_pages_dir / f"{pg}.regions.json"
            if out_json.exists():
                if on_progress:
                    on_progress("regions", i + 1, total)
                continue
            page_png = pages_dir / f"{pg}.png"
            try:
                page_regions = extract_page_regions(
                    docling,
                    page=pg,
                    page_image=page_png,
                    pdf_path=pdf_path,
                    out_dir=gold_pages_dir,
                    client=extractor,
                    model=model,
                )
                out_json.write_text(
                    page_regions.model_dump_json(indent=2), encoding="utf-8"
                )
                region_count += len(page_regions.regions)
            except Exception as e:
                logger.warning("pipeline: region extraction failed p%d %s: %s", pg, slug, e)
            if on_progress:
                on_progress("regions", i + 1, total)

        result["regions"] = region_count
        logger.info("pipeline: %d regions for %s", region_count, slug)

    if on_progress:
        on_progress("done", total, total)

    return result
