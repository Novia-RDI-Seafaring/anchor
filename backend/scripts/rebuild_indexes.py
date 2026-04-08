#!/usr/bin/env python3
"""Rebuild `index.json` for every silver Docling directory.

Usage:
    python backend/scripts/rebuild_indexes.py

Walks backend/data/silver/*/docling.json, runs build_index, writes index.json
next to it. Idempotent — always overwrites.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.silver import (  # noqa: E402
    build_index,
    build_pages_meta,
    render_pages_md,
    render_pages_png,
)

# Override the on-disk root with `ANCHOR_DATA_DIR=…` to keep test runs out of
# `backend/data`. Defaults to the canonical location.
DATA_DIR = Path(os.environ.get("ANCHOR_DATA_DIR") or (ROOT / "data"))
SILVER_DIR = DATA_DIR / "silver"
UPLOADS_DIR = DATA_DIR / "uploads"


def _resolve_pdf_for_slug(slug: str) -> Path | None:
    """Look up the bronze PDF for a silver slug via files_index.json."""
    index_path = UPLOADS_DIR / "files_index.json"
    if not index_path.exists():
        return None
    try:
        entries = json.loads(index_path.read_text())
    except Exception:
        return None
    items = entries.items() if isinstance(entries, dict) else entries
    for _, meta in items:
        if not isinstance(meta, dict):
            continue
        original = meta.get("original_filename") or ""
        # Slug is a normalized form of the original filename used elsewhere.
        normalized = (
            original.lower()
            .removesuffix(".pdf")
            .replace(" ", "-")
            .replace("_", "-")
        )
        if normalized == slug or slug.startswith(normalized):
            path = ROOT / meta.get("file_path", "")
            return path if path.exists() else None
    return None


def main() -> int:
    if not SILVER_DIR.exists():
        print(f"no silver directory at {SILVER_DIR}", file=sys.stderr)
        return 1

    total = 0
    for docling_path in sorted(SILVER_DIR.glob("*/docling.json")):
        slug = docling_path.parent.name
        try:
            docling = json.loads(docling_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [skip] {slug}: failed to parse docling.json: {exc}")
            continue

        index = build_index(docling, filename=f"{slug}.pdf", title=slug.replace("-", " "))
        index_path = docling_path.with_name("index.json")
        index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

        meta = build_pages_meta(docling)
        (docling_path.with_name("pages.meta.json")).write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        pages_dir = docling_path.parent / "pages"
        pages_dir.mkdir(exist_ok=True)
        page_md = render_pages_md(docling)
        for page_no, md in page_md.items():
            (pages_dir / f"{page_no}.md").write_text(md, encoding="utf-8")

        png_count = 0
        pdf_path = _resolve_pdf_for_slug(slug)
        if pdf_path:
            try:
                png_count = len(render_pages_png(pdf_path, pages_dir))
            except Exception as exc:
                print(f"  [warn] {slug}: png render failed: {exc}")

        print(
            f"  [ok]   {slug}: outline={len(index['outline'])}, "
            f"tables={len(index['tables'])}, figures={len(index['figures'])}, "
            f"pages={index['document']['page_count']}, "
            f"md={len(page_md)}, png={png_count}"
        )
        total += 1

    print(f"\nrebuilt {total} index(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
