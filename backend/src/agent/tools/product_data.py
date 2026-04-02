"""Gold-layer product data — load pre-extracted structured data for a document."""
import json
from pathlib import Path

from pydantic_ai import ToolReturn
from pydantic_ai._run_context import RunContext

from ..deps import AgentDeps
from ..helpers import _snapshot

GOLD_DIR = Path(__file__).resolve().parents[3] / "data" / "gold"

_cache: dict[str, dict] = {}


def _load_all() -> dict[str, dict]:
    """Load all gold JSON files, keyed by filename. Cached after first read."""
    if not _cache:
        for path in GOLD_DIR.glob("*.json"):
            data = json.loads(path.read_text())
            filename = data.get("document", {}).get("filename", "")
            if filename:
                _cache[filename] = data
    return _cache


def _find_by_filename(filename: str) -> dict | None:
    """Find gold data matching a document filename (flexible matching)."""
    all_data = _load_all()
    # Exact match first
    if filename in all_data:
        return all_data[filename]
    # Case-insensitive exact match
    filename_lower = filename.lower()
    for key, data in all_data.items():
        if key.lower() == filename_lower:
            return data
    # Stem match — strip extension and compare stems (handles extra suffixes like ---ese00263)
    stem = filename_lower.removesuffix(".pdf")
    for key in all_data:
        key_stem = key.lower().removesuffix(".pdf")
        if key_stem.startswith(stem) or stem.startswith(key_stem):
            return all_data[key]
    return None


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
