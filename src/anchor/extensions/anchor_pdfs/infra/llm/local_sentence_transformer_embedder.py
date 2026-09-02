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
import threading
from typing import Any

DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


class LocalSentenceTransformerEmbedder:
    def __init__(self, model: str = DEFAULT_EMBED_MODEL) -> None:
        self.model_id = model
        self._model: Any = None
        self._dim: int | None = None
        self._load_error: Exception | None = None
        self._load_lock = threading.Lock()
        # Start loading immediately so the first embed() call doesn't pay the
        # full cold-start cost (importing torch + sentence-transformers can take
        # 30–60 s on some machines).
        threading.Thread(target=self._preload, daemon=True).start()

    @property
    def dim(self) -> int | None:
        return self._dim

    def _preload(self) -> None:
        # Eager warm-up runs in a daemon thread. It must NEVER let an exception
        # escape: an unhandled exception in a background thread (e.g. a failed
        # HuggingFace model download) aborts the interpreter at teardown with
        # exit code 134 on Linux/CI. The error is captured here and re-raised
        # from embed(), where a caller can actually handle it. See issue #237.
        try:
            self._ensure_loaded()
        except Exception:  # noqa: BLE001 - stored in _load_error, re-raised on embed()
            pass

    def _ensure_loaded(self) -> None:
        with self._load_lock:
            if self._model is not None:
                return
            if self._load_error is not None:
                raise self._load_error
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.model_id)
            except Exception as exc:
                # Remember the failure so both the eager preload thread and a
                # later embed() see the same error instead of retrying a load
                # that will fail again (and re-spawning failing download threads).
                self._load_error = exc
                raise

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await asyncio.to_thread(self._embed_sync, texts)

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        self._ensure_loaded()
        vecs = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        if self._dim is None and len(vecs) > 0:
            self._dim = int(vecs.shape[1])
        return [v.tolist() for v in vecs]
