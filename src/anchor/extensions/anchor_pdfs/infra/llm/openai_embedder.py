"""Embedder backed by OpenAI embeddings API."""
from __future__ import annotations

import asyncio


class OpenAIEmbedder:
    def __init__(self, api_key: str | None = None, *, model: str = "text-embedding-3-large", base_url: str | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.model_id = model
        self.base_url = base_url

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._sync, texts)

    def _sync(self, texts: list[str]) -> list[list[float]]:
        from .openai_client import make_openai_client

        client = make_openai_client(self.api_key, self.base_url)
        rsp = client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in rsp.data]
