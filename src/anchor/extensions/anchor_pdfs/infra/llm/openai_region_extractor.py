"""RegionExtractor backed by OpenAI vision."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class OpenAIRegionExtractor:
    def __init__(self, api_key: str | None = None, *, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url

    async def extract_page(
        self,
        *,
        page_image: bytes,
        page_no: int,
        docling_items: list[dict[str, Any]],
        model: str,
        page_size: list[float] | None = None,
        dpi: int | None = None,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._sync, page_image, page_no, docling_items, model, page_size, dpi,
        )

    def _sync(self, page_image, page_no, items, model, page_size=None, dpi=None):
        from .openai_client import make_openai_client

        client = make_openai_client(self.api_key, self.base_url)
        b64 = base64.b64encode(page_image).decode()
        prompt = (
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
            f"\nDocling items (id, label, bbox in points, text):\n{json.dumps(items)[:8000]}"
        )
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }]
        try:
            rsp = client.chat.completions.create(
                model=model, messages=messages, response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001
            # Some OpenAI-compatible endpoints — older Azure deployments, some
            # local servers — reject response_format=json_object. Retry without
            # it: the prompt still asks for JSON and we extract it below.
            if "response_format" in str(exc).lower() or getattr(exc, "status_code", None) == 400:
                rsp = client.chat.completions.create(model=model, messages=messages)
            else:
                raise
        body = rsp.choices[0].message.content or "{}"
        try:
            return list(json.loads(body).get("regions", []))
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", body, flags=re.DOTALL)
            if match:
                try:
                    return list(json.loads(match.group(0)).get("regions", []))
                except json.JSONDecodeError:
                    # Fall through to an empty extraction when the model
                    # returned neither direct JSON nor an embedded object.
                    pass
            # Do not swallow malformed output silently: a page that ends up
            # with zero regions because the model returned non-JSON is a
            # quality problem the operator should be able to see. The
            # caller also reports per-page region counts in the ingest
            # result, so this page shows up as region_count=0 there.
            logger.warning(
                "region extraction on page %s (model %s) returned non-JSON output; "
                "persisting zero regions for this page. First 200 chars: %r",
                page_no, model, body[:200],
            )
            return []


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
