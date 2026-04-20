"""Anchor Ingestion CLI — ingest PDFs, check status, query extracted data.

Usage:
    anchor-ingest --data-dir ./data ingest my-doc.pdf
    anchor-ingest --data-dir ./data status my-doc
    anchor-ingest --data-dir ./data list
    anchor-ingest --data-dir ./data index my-doc
    anchor-ingest --data-dir ./data regions my-doc [--page 2]
    anchor-ingest --data-dir ./data page-text my-doc 2
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path


def _slugify(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower() or "doc"


def _find_slug(data_dir: Path, name: str) -> str:
    """Resolve a name to a slug — accepts slug, filename, or PDF path."""
    slug = _slugify(Path(name).stem)
    if (data_dir / "silver" / slug).exists():
        return slug
    # Try exact match
    silver = data_dir / "silver"
    if silver.is_dir():
        for d in silver.iterdir():
            if d.is_dir() and slug in d.name:
                return d.name
    return slug


def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingest a PDF through the full pipeline."""
    from .pipeline import run_full_pipeline

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    data_dir = Path(args.data_dir).resolve()

    # Copy to bronze
    bronze_dir = data_dir / "bronze"
    bronze_dir.mkdir(parents=True, exist_ok=True)
    bronze_path = bronze_dir / pdf_path.name
    if not bronze_path.exists():
        import shutil
        shutil.copy2(pdf_path, bronze_path)
        print(f"Bronze: copied to {bronze_path}")

    slug = args.slug or _slugify(pdf_path.stem)

    def on_progress(stage: str, current: int, total: int) -> None:
        if stage == "done":
            print(f"\nDone! ({total} pages)")
        else:
            print(f"  {stage}: {current}/{total}", end="\r")

    print(f"Ingesting {pdf_path.name} → {slug}")
    result = run_full_pipeline(
        pdf_path,
        data_dir,
        slug=slug,
        dpi=args.dpi,
        polish=not args.skip_polish,
        regions=not args.skip_regions,
        model=args.model,
        on_progress=on_progress,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all ingested documents."""
    data_dir = Path(args.data_dir).resolve()
    silver = data_dir / "silver"
    gold = data_dir / "gold"

    if not silver.is_dir():
        print("No documents ingested yet.")
        return 0

    docs = []
    for d in sorted(silver.iterdir()):
        if not d.is_dir():
            continue
        slug = d.name
        index_path = d / "index.json"
        page_count = 0
        title = slug
        if index_path.exists():
            idx = json.loads(index_path.read_text())
            page_count = idx.get("document", {}).get("page_count", 0)
            title = idx.get("document", {}).get("title", slug)

        has_gold = (gold / slug / "pages").is_dir() if gold.is_dir() else False
        region_count = 0
        if has_gold:
            for rf in (gold / slug / "pages").glob("*.regions.json"):
                rdata = json.loads(rf.read_text())
                region_count += len(rdata.get("regions", []))

        docs.append({
            "slug": slug,
            "title": title,
            "pages": page_count,
            "silver": True,
            "gold": has_gold,
            "regions": region_count,
        })

    if args.json:
        print(json.dumps(docs, indent=2))
    else:
        for doc in docs:
            gold_str = f"  gold: {doc['regions']} regions" if doc["gold"] else "  (no gold)"
            print(f"  {doc['slug']}  ({doc['pages']} pages){gold_str}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show pipeline status for a document."""
    data_dir = Path(args.data_dir).resolve()
    slug = _find_slug(data_dir, args.name)

    status: dict = {"slug": slug, "bronze": False, "silver": False, "gold": False}

    # Bronze
    bronze = data_dir / "bronze"
    if bronze.is_dir():
        for f in bronze.iterdir():
            if _slugify(f.stem) == slug:
                status["bronze"] = True
                status["pdf"] = str(f)
                break

    # Silver
    silver_dir = data_dir / "silver" / slug
    if silver_dir.is_dir():
        status["silver"] = True
        status["silver_files"] = [f.name for f in sorted(silver_dir.iterdir()) if f.is_file()]
        pages_dir = silver_dir / "pages"
        if pages_dir.is_dir():
            status["page_pngs"] = len(list(pages_dir.glob("*.png")))
            status["page_mds"] = len(list(pages_dir.glob("*.md"))) - len(list(pages_dir.glob("*.raw.md")))

    # Gold
    gold_dir = data_dir / "gold" / slug
    if gold_dir.is_dir() and (gold_dir / "pages").is_dir():
        status["gold"] = True
        region_files = list((gold_dir / "pages").glob("*.regions.json"))
        status["gold_pages"] = len(region_files)
        total_regions = 0
        for rf in region_files:
            rdata = json.loads(rf.read_text())
            total_regions += len(rdata.get("regions", []))
        status["gold_regions"] = total_regions

    print(json.dumps(status, indent=2))
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    """Get the silver index for a document."""
    data_dir = Path(args.data_dir).resolve()
    slug = _find_slug(data_dir, args.name)

    index_path = data_dir / "silver" / slug / "index.json"
    if not index_path.exists():
        print(f"Error: no index for '{slug}'", file=sys.stderr)
        return 1

    data = json.loads(index_path.read_text())
    print(json.dumps(data, indent=2))
    return 0


def cmd_regions(args: argparse.Namespace) -> int:
    """Get gold regions for a document."""
    data_dir = Path(args.data_dir).resolve()
    slug = _find_slug(data_dir, args.name)

    gold_pages = data_dir / "gold" / slug / "pages"
    if not gold_pages.is_dir():
        print(f"Error: no gold data for '{slug}'", file=sys.stderr)
        return 1

    result: dict = {"slug": slug, "pages": {}}
    for rf in sorted(gold_pages.glob("*.regions.json")):
        rdata = json.loads(rf.read_text())
        page = rdata.get("page", 0)
        if args.page and page != args.page:
            continue
        result["pages"][page] = rdata.get("regions", [])

    print(json.dumps(result, indent=2))
    return 0


def cmd_page_text(args: argparse.Namespace) -> int:
    """Get the markdown text for a specific page."""
    data_dir = Path(args.data_dir).resolve()
    slug = _find_slug(data_dir, args.name)

    md_path = data_dir / "silver" / slug / "pages" / f"{args.page}.md"
    if not md_path.exists():
        raw_path = data_dir / "silver" / slug / "pages" / f"{args.page}.raw.md"
        if raw_path.exists():
            md_path = raw_path
        else:
            print(f"Error: no text for page {args.page} of '{slug}'", file=sys.stderr)
            return 1

    print(md_path.read_text())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="anchor-ingest",
        description="Anchor Ingestion Pipeline — ingest PDFs, query extracted data",
    )
    parser.add_argument(
        "--data-dir", "-d",
        default="./data",
        help="Root data directory (default: ./data)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest a PDF through the full pipeline")
    p_ingest.add_argument("pdf", help="Path to PDF file")
    p_ingest.add_argument("--slug", help="Override slug name")
    p_ingest.add_argument("--dpi", type=int, default=150)
    p_ingest.add_argument("--model", default="gpt-5.4")
    p_ingest.add_argument("--skip-polish", action="store_true")
    p_ingest.add_argument("--skip-regions", action="store_true")

    # list
    p_list = sub.add_parser("list", help="List all ingested documents")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    # status
    p_status = sub.add_parser("status", help="Show pipeline status for a document")
    p_status.add_argument("name", help="Document slug or filename")

    # index
    p_index = sub.add_parser("index", help="Get silver index (outline, tables, figures)")
    p_index.add_argument("name", help="Document slug or filename")

    # regions
    p_regions = sub.add_parser("regions", help="Get gold regions")
    p_regions.add_argument("name", help="Document slug or filename")
    p_regions.add_argument("--page", type=int, help="Filter to specific page")

    # page-text
    p_page = sub.add_parser("page-text", help="Get markdown text for a page")
    p_page.add_argument("name", help="Document slug or filename")
    p_page.add_argument("page", type=int, help="Page number")

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    handlers = {
        "ingest": cmd_ingest,
        "list": cmd_list,
        "status": cmd_status,
        "index": cmd_index,
        "regions": cmd_regions,
        "page-text": cmd_page_text,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
