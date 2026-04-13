#!/usr/bin/env python3
"""Re-run the full ingestion pipeline for all existing silver documents.

Usage:
    uv run python scripts/reingest_all.py [--model gpt-5.4] [--dpi 150]
                                          [--skip-polish] [--skip-regions]
                                          [--build-graph] [--build-queries]
                                          [--all-post] [--force]

Walks `data/silver/*/docling.json`, finds the matching bronze PDF, and runs
each stage. Stages that already produced output are skipped unless `--force`.

This is the batch version of `run_pipeline.py` — same stages, many docs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.silver import (  # noqa: E402
    build_index,
    build_pages_meta,
    needs_polish,
    polish_pages_md,
    render_pages_md,
    render_pages_png,
)
from src.ingestion.gold import extract_page_regions  # noqa: E402

DATA_DIR = Path(os.environ.get("ANCHOR_DATA_DIR") or (ROOT / "data"))
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
UPLOADS_DIR = DATA_DIR / "uploads"


def _find_pdf(slug: str) -> Path | None:
    """Find the source PDF for a silver slug."""
    # Direct match in uploads
    for ext in (".pdf", ".PDF"):
        candidate = UPLOADS_DIR / f"{slug}{ext}"
        if candidate.exists():
            return candidate

    # Try files_index.json
    index_path = UPLOADS_DIR / "files_index.json"
    if index_path.exists():
        try:
            entries = json.loads(index_path.read_text())
        except Exception:
            return None
        items = entries.items() if isinstance(entries, dict) else entries
        for _, meta in items:
            if not isinstance(meta, dict):
                continue
            original = meta.get("original_filename") or ""
            file_path = meta.get("file_path") or ""
            normalized = (
                original.lower().removesuffix(".pdf").replace(" ", "-").replace("_", "-")
            )
            if normalized == slug or slug.startswith(normalized):
                p = ROOT / file_path if not Path(file_path).is_absolute() else Path(file_path)
                if p.exists():
                    return p
                # Also check uploads dir directly
                p2 = UPLOADS_DIR / Path(file_path).name
                if p2.exists():
                    return p2

    # Check any PDF whose stem slugifies to match
    for pdf in UPLOADS_DIR.glob("*.pdf"):
        import re
        pdf_slug = re.sub(r"[^a-zA-Z0-9]+", "-", pdf.stem).strip("-").lower()
        if pdf_slug == slug:
            return pdf

    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="gpt-5.4")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--skip-polish", action="store_true")
    p.add_argument("--skip-regions", action="store_true")
    p.add_argument("--build-graph", action="store_true")
    p.add_argument("--build-queries", action="store_true")
    p.add_argument("--all-post", action="store_true")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    if args.all_post:
        args.build_graph = True
        args.build_queries = True

    if not SILVER_DIR.exists():
        print(f"no silver directory at {SILVER_DIR}", file=sys.stderr)
        return 1

    slugs = sorted(
        d.parent.name for d in SILVER_DIR.glob("*/docling.json")
    )
    print(f"found {len(slugs)} silver doc(s): {slugs}\n")

    for slug in slugs:
        silver_dir = SILVER_DIR / slug
        pages_dir = silver_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        gold_dir = GOLD_DIR / slug
        gold_pages_dir = gold_dir / "pages"
        gold_pages_dir.mkdir(parents=True, exist_ok=True)

        docling = json.loads((silver_dir / "docling.json").read_text())
        pdf_path = _find_pdf(slug)

        needed_pages = sorted({
            int(it["page"])
            for it in docling.get("items", [])
            if isinstance(it, dict) and isinstance(it.get("page"), (int, float))
        })

        print(f"▶ {slug} ({len(needed_pages)} pages)")

        # Silver: index + pages.meta (always rebuild — cheap)
        index = build_index(docling, filename=f"{slug}.pdf", title=slug.replace("-", " "))
        (silver_dir / "index.json").write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        meta = build_pages_meta(docling)
        (silver_dir / "pages.meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Silver: PNGs
        if pdf_path:
            missing = [pg for pg in needed_pages if not (pages_dir / f"{pg}.png").exists()]
            if args.force or missing:
                render_pages_png(pdf_path, pages_dir, dpi=args.dpi)
                print(f"  [silver] rendered {len(needed_pages)} PNGs")
        else:
            print(f"  [silver] no PDF found — skipping PNGs, polish, regions")

        # Silver: raw md
        seed = render_pages_md(docling)
        for pg, md in seed.items():
            (pages_dir / f"{pg}.raw.md").write_text(md, encoding="utf-8")

        # Silver: polish
        if args.skip_polish or not pdf_path:
            for pg, md in seed.items():
                md_path = pages_dir / f"{pg}.md"
                if not md_path.exists():
                    md_path.write_text(md, encoding="utf-8")
        else:
            from src.ingestion.openai_clients import OpenAIPageMdPolisher
            polisher = OpenAIPageMdPolisher()
            polished = polish_pages_md(
                docling,
                pages_png_dir=pages_dir,
                deterministic_md=seed,
                client=polisher,
                model=args.model,
            )
            for pg, md in polished.items():
                (pages_dir / f"{pg}.md").write_text(md, encoding="utf-8")
            plan = [pg for pg in needed_pages if needs_polish(docling, pg)]
            print(f"  [silver] polished {len(plan)} page(s)")

        # Gold: regions
        if args.skip_regions or not pdf_path:
            pass
        else:
            from src.ingestion.openai_clients import OpenAIRegionExtractor
            extractor = OpenAIRegionExtractor()
            for pg in needed_pages:
                out_json = gold_pages_dir / f"{pg}.regions.json"
                if not args.force and out_json.exists():
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
                        model=args.model,
                    )
                except Exception as e:
                    print(f"    p{pg}: FAILED ({type(e).__name__}: {e})")
                    continue
                out_json.write_text(page_regions.model_dump_json(indent=2), encoding="utf-8")
            region_count = len(list(gold_pages_dir.glob("*.regions.json")))
            print(f"  [gold] {region_count} page(s) with regions")

        print(f"  done\n")

    # Post-processing across all docs
    if args.build_graph:
        from src.ingestion.knowledge_graph import build_and_save
        graph_path = build_and_save(DATA_DIR)
        print(f"[graph] wrote {graph_path}")

    if args.build_queries:
        from src.ingestion.query_index import build_and_save as build_queries
        qi_path = build_queries(DATA_DIR, model=args.model)
        qi = json.loads(qi_path.read_text())
        print(f"[queries] {len(qi)} query templates")

    print(f"\n✓ done — processed {len(slugs)} document(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
