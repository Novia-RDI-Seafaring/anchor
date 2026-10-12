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


def region_prompt(page_no: int, docling_items: list[dict[str, Any]]) -> str:
    return (
        f"List the visual regions on page {page_no} of this engineering PDF. "
        "For each region emit: id, kind (chart|spec_block|table|figure|diagram|text), "
        "title, description, approximate bbox [left, top, right, bottom] in top-left "
        "PDF points (origin at the page's top-left corner, y increasing downward), "
        "tags[], entities[]. For tables and spec blocks, make regions tight: split "
        "distinct visual sections or sub-tables separated by headers, whitespace, or rules. "
        "Do not merge adjacent sub-tables, and keep values from neighboring groups out of "
        "the region. In the description, list exact visible facts as 'key: value' pairs "
        "when the region contains key/value rows. Include the value for every key you can "
        "read; if two keys share the same value, repeat that value for both keys. Do not "
        "deduplicate equal values or summarize numeric values. Return JSON with key "
        "'regions'.\n"
        f"\nDocling items:\n{json.dumps(docling_items)[:ITEMS_CHAR_LIMIT]}"
    )


def polish_prompt(page_no: int, deterministic_md: str, docling_items: list[dict[str, Any]]) -> str:
    return (
        "You are polishing a per-page markdown rendering. Use the page image "
        "and the docling items as ground truth. Keep all text faithful; only "
        f"clean structure. Page {page_no}.\n\nSeed markdown:\n{deterministic_md}\n"
        "\n\nDocling items:\n" + json.dumps(docling_items)[:ITEMS_CHAR_LIMIT]
    )
