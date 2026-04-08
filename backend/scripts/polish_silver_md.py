#!/usr/bin/env python3
"""Polish a silver doc's per-page markdown with the OpenAI vision client.

Usage:
    uv run python scripts/polish_silver_md.py <slug> [--model gpt-5.4] [--pages 1,2,7]
    uv run python scripts/polish_silver_md.py <slug> --pdf path/to/source.pdf

Reads `data/silver/<slug>/docling.json`, makes sure `pages/N.png` exists
(rendering them on-the-fly from the PDF if they don't), then runs the
polisher and writes back to `pages/N.md`. The deterministic raw md is
preserved as `pages/N.raw.md`.

Skips pages that don't need polishing per `silver.needs_polish`. Override
with `--pages` to force a specific subset.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.openai_clients import OpenAIPageMdPolisher  # noqa: E402
from src.ingestion.silver import (  # noqa: E402
    needs_polish,
    polish_pages_md,
    render_pages_md,
    render_pages_png,
)

DATA_DIR = Path(os.environ.get("ANCHOR_DATA_DIR") or (ROOT / "data"))
SILVER_DIR = DATA_DIR / "silver"


def _parse_pages(arg: str | None) -> list[int] | None:
    if not arg:
        return None
    return [int(p) for p in arg.split(",") if p.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("slug", help="silver dir name (e.g. alfa-laval-lkh-centrifugal-pump)")
    p.add_argument("--model", default="gpt-5.4")
    p.add_argument("--pdf", help="bronze PDF path (used to render page PNGs if missing)")
    p.add_argument("--pages", help="comma-separated 1-indexed pages to force-polish")
    p.add_argument("--dpi", type=int, default=150)
    args = p.parse_args()

    slug = args.slug
    silver_doc = SILVER_DIR / slug
    docling_path = silver_doc / "docling.json"
    if not docling_path.exists():
        print(f"no silver dir at {silver_doc}", file=sys.stderr)
        return 1

    docling = json.loads(docling_path.read_text())
    pages_dir = silver_doc / "pages"
    pages_dir.mkdir(exist_ok=True)

    # Make sure page PNGs exist (the polisher needs them).
    needed_pages = sorted({
        int(it["page"]) for it in docling.get("items", [])
        if isinstance(it, dict) and isinstance(it.get("page"), (int, float))
    })
    missing_pngs = [pg for pg in needed_pages if not (pages_dir / f"{pg}.png").exists()]
    if missing_pngs:
        if not args.pdf:
            print(
                f"missing page PNGs for pages {missing_pngs} and no --pdf given",
                file=sys.stderr,
            )
            return 2
        pdf_path = Path(args.pdf)
        print(f"rendering {len(needed_pages)} page(s) at {args.dpi} dpi from {pdf_path.name}…")
        render_pages_png(pdf_path, pages_dir, dpi=args.dpi)

    # Build the deterministic seed (and snapshot it as .raw.md so we can compare).
    seed = render_pages_md(docling)
    for pg, md in seed.items():
        (pages_dir / f"{pg}.raw.md").write_text(md, encoding="utf-8")

    only_pages = _parse_pages(args.pages)
    polisher = OpenAIPageMdPolisher()

    plan = [
        pg for pg in needed_pages
        if (only_pages and pg in only_pages) or needs_polish(docling, pg)
    ]
    print(f"will polish pages: {plan}")

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
        kind = "polished" if pg in plan else "seed   "
        print(f"  [{kind}] page {pg}: {len(md.splitlines())} lines")

    print(f"done — {len(plan)} polished, {len(polished) - len(plan)} unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
