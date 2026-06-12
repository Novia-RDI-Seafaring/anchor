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
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._sync, page_image, page_no, docling_items, model)

    def _sync(self, page_image, page_no, items, model):
        from .openai_client import make_openai_client

        client = make_openai_client(self.api_key, self.base_url)
        b64 = base64.b64encode(page_image).decode()
        prompt = (
            f"List the visual regions on page {page_no} of this engineering PDF. "
            "For each region emit: id, kind (chart|spec_block|table|figure|diagram|text), "
            "title, description, approximate bbox [left, top, right, bottom] in BOTTOMLEFT coords, "
            "tags[], entities[]. Return JSON with key 'regions'.\n"
            f"\nDocling items:\n{json.dumps(items)[:8000]}"
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
