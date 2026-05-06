"""Embedder backed by OpenAI embeddings API."""
from __future__ import annotations

import asyncio


class OpenAIEmbedder:
    def __init__(self, api_key: str | None = None, *, model: str = "text-embedding-3-large", base_url: str | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._sync, texts)

    def _sync(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url) if self.api_key else OpenAI()
        rsp = client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in rsp.data]
