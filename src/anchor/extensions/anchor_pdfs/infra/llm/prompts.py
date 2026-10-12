"""The page prompts every vision backend sends, so all of them ask the same thing.

The OpenAI-compatible clients and the agent-CLI providers (``claude``,
``codex``) differ in transport only. Keeping the wording here means a change
to what a region is lands on every backend at once.
"""
from __future__ import annotations

import json
from typing import Any

#: Docling items are context, not the payload; cap them so a dense page does
#: not crowd out the instructions.
ITEMS_CHAR_LIMIT = 8000


def region_prompt(
    page_no: int,
    docling_items: list[dict[str, Any]],
    *,
    page_size: list[float] | None = None,
    dpi: int | None = None,
) -> str:
    """Ask for regions named by Docling item ids, with a bbox only as a fallback.

    ``page_size`` (points) and ``dpi`` tell the model what frame the image is
    in, so any bbox it does give lands in points, not pixels.
    """
    return (
        f"List the visual regions on page {page_no} of this engineering PDF. "
        "For each region emit, as top-level fields of the region object: id, kind "
        "(chart|spec_block|table|figure|diagram|text), title, description, tags[], "
        "entities[], and its geometry as either member_item_ids[] or bbox. "
        f"{_frame_sentence(page_size, dpi)}"
        "member_item_ids names the Docling items the region covers (their ids, "
        "from the list below); that is the preferred way, and the server computes "
        "the box from them. Only when no item covers a visual, give an approximate "
        "bbox [left, top, right, bottom] in top-left PDF points (origin at the "
        "page's top-left corner, y increasing downward), never in image pixels. "
        "One region covers one block: a table or picture "
        "belongs to exactly one region, and a region names only the items of its "
        "own block, not the heading or table that follows it. For tables and spec "
        "blocks, make regions tight: split distinct visual sections or sub-tables "
        "separated by headers, whitespace, or rules. Do not merge adjacent "
        "sub-tables, and keep values from neighboring groups out of the region. In "
        "the description, list exact visible facts as 'key: value' pairs when the "
        "region contains key/value rows. Include the value for every key you can "
        "read; if two keys share the same value, repeat that value for both keys. "
        "Do not deduplicate equal values or summarize numeric values. Return JSON "
        "with key 'regions'.\n"
        f"\nDocling items (id, label, bbox in points, text):\n"
        f"{json.dumps(docling_items)[:ITEMS_CHAR_LIMIT]}"
    )


def polish_prompt(page_no: int, deterministic_md: str, docling_items: list[dict[str, Any]]) -> str:
    return (
        "You are polishing a per-page markdown rendering. Use the page image "
        "and the docling items as ground truth. Keep all text faithful; only "
        f"clean structure. Page {page_no}.\n\nSeed markdown:\n{deterministic_md}\n"
        "\n\nDocling items:\n" + json.dumps(docling_items)[:ITEMS_CHAR_LIMIT]
    )


def _frame_sentence(page_size: list[float] | None, dpi: int | None) -> str:
    """Tell the model what it is looking at, so its boxes land in points.

    A vision model given a raster and asked for points guesses the frame
    unless told: pixels on one page, points on the next. Saying the page
    size, the raster size and the scale removes the guess.
    """
    if not page_size or len(page_size) != 2:
        return ""
    width, height = float(page_size[0]), float(page_size[1])
    sentence = f"The page is {width:.1f} x {height:.1f} PDF points. "
    if dpi:
        scale = dpi / 72.0
        sentence += (
            f"The attached image is this page rendered at {dpi} dpi, "
            f"{round(width * scale)} x {round(height * scale)} px, so 1 pt = {scale:.3f} px; "
            "the Docling items' bboxes are in points, not in these pixels. "
        )
    return sentence
