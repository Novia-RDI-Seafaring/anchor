"""Embedder backed by sentence-transformers — local, no API key.

Default model is ``BAAI/bge-small-en-v1.5`` (384-d, ~33 MB ONNX). Chosen
because it has both a Python (sentence-transformers) and an in-browser
(@xenova/transformers, WASM/ONNX) path, so the *same* model id can embed
documents at ingest and embed user queries inside the browser — vectors
share an embedding space.

The model id is exposed via ``model_id`` so callers can record it in
``embeddings.json`` metadata; switching models invalidates existing
vectors so storing the model id is non-negotiable.
"""
from __future__ import annotations

import asyncio
from typing import Any


DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


class LocalSentenceTransformerEmbedder:
    def __init__(self, model: str = DEFAULT_EMBED_MODEL) -> None:
        self.model_id = model
        self._model: Any = None  # lazy-loaded
        self._dim: int | None = None

    @property
    def dim(self) -> int | None:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._embed_sync, texts)

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_id)
        vecs = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        if self._dim is None and len(vecs) > 0:
            self._dim = int(vecs.shape[1])
        return [v.tolist() for v in vecs]
