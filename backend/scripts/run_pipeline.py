#!/usr/bin/env python3
"""End-to-end ingestion pipeline: PDF → bronze → silver → gold.

Usage:
    uv run python scripts/run_pipeline.py <pdf> <out_dir> [--slug NAME]
                                          [--dpi 150] [--model gpt-5.4]
                                          [--skip-polish] [--skip-regions]
                                          [--pages 1,2] [--force]

Output layout (under <out_dir>):
    bronze/<slug>.pdf                         copy of the source PDF
    silver/<slug>/docling.json                flat docling items
    silver/<slug>/index.json                  navigable outline + tables
    silver/<slug>/pages.meta.json             per-page item summary
    silver/<slug>/pages/N.png                 rendered page image
    silver/<slug>/pages/N.raw.md              deterministic md seed
    silver/<slug>/pages/N.md                  polished md (or = .raw.md)
    gold/<slug>/pages/N.regions.json          validated region list
    gold/<slug>/pages/N/r*.png|.svg           cropped region assets

`--skip-polish` and `--skip-regions` let you iterate on one stage at a time.
`--force` re-runs stages even when their outputs already exist.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.bronze import pdf_to_silver  # noqa: E402
from src.ingestion.gold import extract_page_regions  # noqa: E402
from src.ingestion.silver import (  # noqa: E402
    build_index,
    build_pages_meta,
    polish_pages_md,
    render_pages_md,
    render_pages_png,
)


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return s or "doc"


def _parse_pages(arg: str | None) -> list[int] | None:
    if not arg:
        return None
    return [int(p) for p in arg.split(",") if p.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("pdf", type=Path, help="source PDF path")
    p.add_argument("out_dir", type=Path, help="output root (bronze/silver/gold land here)")
    p.add_argument("--slug", help="override slug (default: derived from pdf stem)")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--model", default="gpt-5.4")
    p.add_argument("--pages", help="comma-separated 1-indexed page subset")
    p.add_argument("--skip-polish", action="store_true")
    p.add_argument("--skip-regions", action="store_true")
    p.add_argument("--build-graph", action="store_true", help="build knowledge graph from gold regions")
    p.add_argument("--embed", action="store_true", help="embed gold regions for semantic search")
    p.add_argument("--build-queries", action="store_true", help="generate + embed Q&A index from gold regions")
    p.add_argument("--all-post", action="store_true", help="shortcut for --build-graph --embed --build-queries")
    p.add_argument("--force", action="store_true", help="re-run stages even if outputs exist")
    args = p.parse_args()

    pdf: Path = args.pdf.resolve()
    if not pdf.exists():
        print(f"error: pdf not found: {pdf}", file=sys.stderr)
        return 1

    out: Path = args.out_dir.resolve()
    slug = args.slug or _slugify(pdf.stem)
    only_pages = _parse_pages(args.pages)

    bronze_dir = out / "bronze"
    silver_dir = out / "silver" / slug
    gold_dir = out / "gold" / slug
    pages_dir = silver_dir / "pages"
    gold_pages_dir = gold_dir / "pages"

    for d in (bronze_dir, silver_dir, pages_dir, gold_pages_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"▶ pipeline for {pdf.name} → {out}  (slug={slug})")

    # ── Bronze: copy PDF ────────────────────────────────────────────────
    bronze_pdf = bronze_dir / f"{slug}.pdf"
    if args.force or not bronze_pdf.exists():
        shutil.copy2(pdf, bronze_pdf)
        print(f"  [bronze] copied → {bronze_pdf.relative_to(out)}")
    else:
        print(f"  [bronze] exists, skipping")

    # ── Silver: docling ─────────────────────────────────────────────────
    docling_path = silver_dir / "docling.json"
    if args.force or not docling_path.exists():
        print(f"  [silver] running docling…")
        pdf_to_silver(bronze_pdf, silver_dir)
        print(f"  [silver] wrote {docling_path.relative_to(out)}")
    else:
        print(f"  [silver] docling.json exists, skipping")
    docling = json.loads(docling_path.read_text())

    # ── Silver: index + pages.meta ──────────────────────────────────────
    index = build_index(docling, filename=pdf.name, title=pdf.stem)
    (silver_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    meta = build_pages_meta(docling)
    (silver_dir / "pages.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"  [silver] index.json + pages.meta.json")

    # ── Silver: page PNGs ───────────────────────────────────────────────
    needed_pages = sorted({
        int(it["page"]) for it in docling.get("items", [])
        if isinstance(it, dict) and isinstance(it.get("page"), (int, float))
    })
    missing = [pg for pg in needed_pages if not (pages_dir / f"{pg}.png").exists()]
    if args.force or missing:
        print(f"  [silver] rendering {len(needed_pages)} page PNG(s) @ {args.dpi} dpi…")
        render_pages_png(bronze_pdf, pages_dir, dpi=args.dpi)
    else:
        print(f"  [silver] page PNGs exist, skipping")

    # ── Silver: raw md seed ─────────────────────────────────────────────
    seed = render_pages_md(docling)
    for pg, md in seed.items():
        (pages_dir / f"{pg}.raw.md").write_text(md, encoding="utf-8")
    print(f"  [silver] wrote {len(seed)} raw .md seed(s)")

    # ── Silver: polish via OpenAI ───────────────────────────────────────
    if args.skip_polish:
        print("  [silver] polish skipped (--skip-polish); using raw seed as .md")
        for pg, md in seed.items():
            (pages_dir / f"{pg}.md").write_text(md, encoding="utf-8")
    else:
        from src.ingestion.openai_clients import OpenAIPageMdPolisher

        print(f"  [silver] polishing md with {args.model}…")
        polisher = OpenAIPageMdPolisher()
        polished = polish_pages_md(
            docling,
            pages_png_dir=pages_dir,
            deterministic_md=seed,
            client=polisher,
            model=args.model,
            only_pages=only_pages,
        )
        for pg, md in polished.items():
            (pages_dir / f"{pg}.md").write_text(md, encoding="utf-8")
        print(f"  [silver] polished {len(polished)} page(s)")

    # ── Gold: regions ───────────────────────────────────────────────────
    if args.skip_regions:
        print("  [gold] regions skipped (--skip-regions)")
    else:
        from src.ingestion.openai_clients import OpenAIRegionExtractor

        extractor = OpenAIRegionExtractor()
        target_pages = only_pages or needed_pages
        print(f"  [gold] extracting regions for pages {target_pages}…")
        for pg in target_pages:
            out_json = gold_pages_dir / f"{pg}.regions.json"
            if not args.force and out_json.exists():
                print(f"    p{pg}: exists, skipping")
                continue
            page_png = pages_dir / f"{pg}.png"
            try:
                page_regions = extract_page_regions(
                    docling,
                    page=pg,
                    page_image=page_png,
                    pdf_path=bronze_pdf,
                    out_dir=gold_pages_dir,
                    client=extractor,
                    model=args.model,
                )
            except Exception as e:  # don't let one bad page kill the run
                print(f"    p{pg}: FAILED ({type(e).__name__}: {e})")
                continue
            out_json.write_text(page_regions.model_dump_json(indent=2), encoding="utf-8")
            print(f"    p{pg}: {len(page_regions.regions)} region(s) → {out_json.relative_to(out)}")

    # ── Resolve --all-post shortcut ──────────────────────────────────────
    if args.all_post:
        args.build_graph = True
        args.embed = True
        args.build_queries = True

    # ── Knowledge graph ──────────────────────────────────────────────────
    if args.build_graph:
        from src.ingestion.knowledge_graph import build_and_save
        graph_path = build_and_save(out)
        print(f"  [graph] wrote {graph_path.relative_to(out)}")

    # ── Embeddings ────────────────────────────────────────────────────────
    if args.embed:
        from src.ingestion.embed import embed_regions
        embeddings_path = out / "embeddings.jsonl"
        count = embed_regions(out / "gold", embeddings_path, model="text-embedding-3-large")
        print(f"  [embed] {count} region(s) embedded → {embeddings_path.relative_to(out)}")

    # ── Q&A query index ─────────────────────────────────────────────────
    if args.build_queries:
        from src.ingestion.query_index import build_and_save as build_queries
        qi_path = build_queries(out, model=args.model)
        qi = json.loads(qi_path.read_text())
        print(f"  [queries] {len(qi)} query templates → {qi_path.relative_to(out)}")

    print("✓ done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
