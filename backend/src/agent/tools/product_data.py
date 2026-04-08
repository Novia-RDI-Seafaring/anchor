"""Gold-layer product data — load pre-extracted structured data for a document."""
import json
import os
from pathlib import Path

from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext

from ..deps import AgentDeps
from ..helpers import _snapshot

# Data dir is configurable so tests (and any alternative deployments) can
# point at a scratch directory instead of the canonical `backend/data`.
# Override with the `ANCHOR_DATA_DIR` env var.
_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
DATA_DIR = Path(os.environ.get("ANCHOR_DATA_DIR") or _DEFAULT_DATA_DIR)
GOLD_DIR = DATA_DIR / "gold"
SILVER_DIR = DATA_DIR / "silver"


def _refresh_data_dir() -> None:
    """Re-read `ANCHOR_DATA_DIR` and clear caches. Tests use this to point
    the loaders at a fresh tmp dir between cases."""
    global DATA_DIR, GOLD_DIR, SILVER_DIR
    DATA_DIR = Path(os.environ.get("ANCHOR_DATA_DIR") or _DEFAULT_DATA_DIR)
    GOLD_DIR = DATA_DIR / "gold"
    SILVER_DIR = DATA_DIR / "silver"
    _gold_cache.clear()
    _index_cache.clear()
    _silver_pages_cache.clear()

_gold_cache: dict[str, dict] = {}
_index_cache: dict[str, dict] = {}
_silver_pages_cache: dict[str, dict[int, str]] = {}
# Back-compat alias — existing callers import `_cache` for tests/inspection.
_cache = _gold_cache


def _load_all() -> dict[str, dict]:
    """Load all gold JSON files, keyed by filename. Cached after first read."""
    if not _gold_cache:
        for path in GOLD_DIR.glob("*.json"):
            data = json.loads(path.read_text())
            filename = data.get("document", {}).get("filename", "")
            if filename:
                _gold_cache[filename] = data
    return _gold_cache


def _load_all_indexes() -> dict[str, dict]:
    """Load all silver index.json files, keyed by filename. Cached after first read."""
    if not _index_cache:
        for path in SILVER_DIR.glob("*/index.json"):
            try:
                data = json.loads(path.read_text())
            except Exception:
                continue
            filename = data.get("document", {}).get("filename", "")
            if filename:
                _index_cache[filename] = data
    return _index_cache


def _match_by_filename(store: dict[str, dict], filename: str) -> dict | None:
    """Flexible filename match (exact, case-insensitive, then stem prefix)."""
    if filename in store:
        return store[filename]
    filename_lower = filename.lower()
    for key, data in store.items():
        if key.lower() == filename_lower:
            return data
    stem = filename_lower.removesuffix(".pdf")
    for key in store:
        key_stem = key.lower().removesuffix(".pdf")
        if key_stem.startswith(stem) or stem.startswith(key_stem):
            return store[key]
    return None


def _find_by_filename(filename: str) -> dict | None:
    """Find gold data matching a document filename."""
    return _match_by_filename(_load_all(), filename)


def _find_index_by_filename(filename: str) -> dict | None:
    """Find silver index data matching a document filename."""
    return _match_by_filename(_load_all_indexes(), filename)


def _load_all_silver_pages() -> dict[str, dict[int, str]]:
    """Load every silver `pages/N.md` file, keyed by document filename."""
    if not _silver_pages_cache:
        for index_path in SILVER_DIR.glob("*/index.json"):
            try:
                index = json.loads(index_path.read_text())
            except Exception:
                continue
            filename = index.get("document", {}).get("filename") or f"{index_path.parent.name}.pdf"
            pages_dir = index_path.parent / "pages"
            if not pages_dir.exists():
                continue
            page_md: dict[int, str] = {}
            for md_path in pages_dir.glob("*.md"):
                try:
                    page_no = int(md_path.stem)
                except ValueError:
                    continue
                page_md[page_no] = md_path.read_text(encoding="utf-8")
            if page_md:
                _silver_pages_cache[filename] = page_md
    return _silver_pages_cache


def _find_silver_pages_by_filename(filename: str) -> dict[int, str] | None:
    return _match_by_filename(_load_all_silver_pages(), filename)  # type: ignore[return-value]


def find_product_data_by_filename(filename: str) -> dict | None:
    """Public gold-layer lookup by document filename."""
    return _find_by_filename(filename)


def find_product_index_by_filename(filename: str) -> dict | None:
    """Public silver-index lookup by document filename."""
    return _find_index_by_filename(filename)


def find_silver_pages_by_filename(filename: str) -> dict[int, str] | None:
    """Public per-page silver markdown lookup by document filename."""
    return _find_silver_pages_by_filename(filename)


def build_loaded_documents_context(filenames: list[str]) -> str | None:
    """Build injected context for documents with gold/silver product data."""
    gold_sections: list[str] = []
    index_sections: list[str] = []
    silver_md_sections: list[str] = []

    for filename in filenames:
        gold = find_product_data_by_filename(filename)
        if gold:
            gold_filename = gold.get("document", {}).get("filename", "")
            filename_note = ""
            if gold_filename and gold_filename != filename:
                filename_note = (
                    f"\n**IMPORTANT:** Use filename `{filename}` (not `{gold_filename}`) "
                    f"in all source references for this document.\n"
                )
            gold_sections.append(
                f"### {filename}\n{filename_note}"
                f"```json\n{json.dumps(gold, indent=2, default=str)}\n```"
            )
            continue

        index = find_product_index_by_filename(filename)
        if index:
            index_sections.append(
                f"### {filename}\n"
                f"```json\n{json.dumps(index, indent=2, default=str)}\n```"
            )
            continue

        pages_md = find_silver_pages_by_filename(filename)
        if pages_md:
            joined = "\n\n".join(
                f"#### page {page_no}\n{md.strip()}"
                for page_no, md in sorted(pages_md.items())
            )
            silver_md_sections.append(f"### {filename}\n{joined}")

    parts: list[str] = []
    if gold_sections:
        parts.append(
            "LOADED PRODUCT DATA (gold layer — pre-extracted structured data, authoritative):\n\n"
            + "\n\n".join(gold_sections)
        )
    if index_sections:
        parts.append(
            "DOCUMENT INDEXES (silver layer — outline, tables, figures with page + bbox).\n"
            "Use these to decide which page to open with read_document_page — prefer jumping\n"
            "directly to a relevant table's page + bbox over scanning pages sequentially.\n\n"
            + "\n\n".join(index_sections)
        )
    if silver_md_sections:
        parts.append(
            "SILVER PAGES (per-page markdown — fallback when no gold or index is available).\n\n"
            + "\n\n".join(silver_md_sections)
        )

    return "\n\n".join(parts) if parts else None


async def get_product_data(
    ctx: RunContext[AgentDeps],
    filename: str,
) -> ToolReturn:
    """Load the full pre-extracted product data for a document.

    Returns structured JSON with product family info, per-model specs,
    operating data, dimensions, materials, motor data, etc.
    Use this when a document has gold-layer data available — it's much faster
    and more complete than reading individual pages.

    Args:
        filename: The document filename (e.g. "alfa-laval-lkh-centrifugal-pump---product-leaflet---ese00263.pdf").
                  This is the filename shown in the document list.
    """
    data = _find_by_filename(filename)
    r = _snapshot(ctx)
    if data:
        r.return_value = data
    else:
        r.return_value = {"found": False, "message": "No pre-extracted product data available for this document."}
    return r
