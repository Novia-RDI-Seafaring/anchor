"""PageMdPolisher backed by OpenAI vision-capable chat completions."""
from __future__ import annotations

import asyncio
import base64
from typing import Any

from .prompts import polish_prompt


class OpenAIPageMdPolisher:
    def __init__(self, api_key: str | None = None, *, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url

    async def polish_page(
        self,
        *,
        page_image: bytes,
        page_no: int,
        deterministic_md: str,
        docling_items: list[dict[str, Any]],
        model: str,
    ) -> str:
        return await asyncio.to_thread(
            self._polish_sync, page_image, page_no, deterministic_md, docling_items, model,
        )

    def _polish_sync(self, page_image, page_no, det_md, items, model):
        from .openai_client import make_openai_client

        client = make_openai_client(self.api_key, self.base_url)
        b64 = base64.b64encode(page_image).decode()
        prompt = polish_prompt(page_no, det_md, items)
        rsp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
        )
        return rsp.choices[0].message.content or det_md
