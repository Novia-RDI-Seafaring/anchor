"""Embedder backed by sentence-transformers — local, no API key.

Default model is `all-MiniLM-L6-v2` (384-dim, ~80 MB). Downloaded once on
first use and cached in HuggingFace's standard cache directory.

This is the recommended default: zero-key, runs on CPU, ~10ms/query on
modern hardware, ~80% the retrieval quality of OpenAI text-embedding-3-large.
For higher quality, swap in `OpenAIEmbedder`; for full server-side
parity with browser-side query embeddings, keep this one (Transformers.js
ships the same MiniLM model).
"""
from __future__ import annotations

import asyncio
from typing import Any


class LocalSentenceTransformerEmbedder:
    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.model_name = model
        self._model: Any = None  # lazy-loaded

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed_sync, texts)

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        vecs = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return [v.tolist() for v in vecs]
