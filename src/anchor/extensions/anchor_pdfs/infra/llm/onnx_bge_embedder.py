"""Embedder backed by onnxruntime — local, no API key, no torch.

Default model is ``BAAI/bge-small-en-v1.5`` (384-d, 133 MB fp32 ONNX graph). The model id
is the *same* one the browser embeds queries with: `web/src/search/embedder.ts`
runs `@xenova/transformers` over these same ONNX weights in a Web Worker. Both
sides therefore share one runtime as well as one embedding space, instead of
torch on the server and ONNX in the client.

Why onnxruntime rather than sentence-transformers: importing
``sentence_transformers`` pulls torch + transformers + scipy + sklearn — 4,114
modules, measured at anywhere from 6 s to never finishing on Windows. This
path imports onnxruntime + tokenizers instead, which is far smaller.

Be careful where these imports run. Loading a native extension has been seen
to wedge indefinitely inside ``create_module`` in the MCP server process (0%
CPU, never returns), and ``numpy._core.multiarray`` is the one that bites —
which is why the sentence-transformers embedder hung too; it pulled numpy in
on the way. Placement has real consequences and both ends have been tried:
importing at module scope moved the cost onto the bundle-build path, and
because ``list_tools`` builds a bundle for extension discovery that pushed a
~20 s import into the connect handshake and clients stopped connecting. So the
imports stay deferred to first embed, and :data:`EMBED_TIMEOUT_S` bounds that
call so a wedge surfaces as an error rather than a hang. The underlying wedge
is not solved here — running the model in a separate process is the fix that
would actually remove it.

The model id is exposed via ``model_id`` so callers can record it in
``embeddings.json`` metadata; switching models invalidates existing vectors so
storing the model id is non-negotiable.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"

#: Cap on one embed call, including the first-call import + session build.
#: Loading numpy's native extension has been observed to wedge indefinitely
#: inside ``create_module`` in this process (0% CPU, never returns). A wedged
#: thread cannot be cancelled, so this does not rescue the worker — it returns
#: an honest failure to the caller instead of hanging the request until the
#: client's own timeout fires and leaves it guessing.
EMBED_TIMEOUT_S = 30.0

#: Repo-relative paths of the two artefacts an ONNX embed needs.
_ONNX_WEIGHTS = "onnx/model.onnx"
_TOKENIZER = "tokenizer.json"

#: bge models pool the CLS token (``1_Pooling/config.json`` sets
#: ``pooling_mode_cls_token``), then L2-normalise. Not mean pooling.
_MAX_TOKENS = 512


class OnnxBgeEmbedder:
    """Embed text with a bge ONNX graph via onnxruntime.

    Loading is lazy and single-flight: the first ``embed`` builds the session
    under ``_load_lock``, later calls reuse it. Unlike the torch path this is
    cheap enough that the laziness is an implementation detail rather than a
    scheduling problem.
    """

    def __init__(self, model: str = DEFAULT_EMBED_MODEL) -> None:
        self.model_id = model
        self._session: Any = None
        self._tokenizer: Any = None
        self._dim: int | None = None
        self._load_error: Exception | None = None
        self._load_lock = threading.Lock()

    @property
    def dim(self) -> int | None:
        return self._dim

    def _ensure_loaded(self) -> None:
        with self._load_lock:
            if self._session is not None:
                return
            if self._load_error is not None:
                raise self._load_error
            try:
                # Deferred, not module-level: importing these at module scope
                # put the cost on the bundle-build path, and `list_tools`
                # builds a bundle for extension discovery — which pushed a
                # ~20 s import into the MCP connect handshake and stopped
                # clients connecting at all. Keep the connect path clean and
                # pay the cost on first embed, bounded by EMBED_TIMEOUT_S.
                import onnxruntime
                from huggingface_hub import hf_hub_download
                from tokenizers import Tokenizer

                weights = hf_hub_download(self.model_id, _ONNX_WEIGHTS)
                tokenizer_json = hf_hub_download(self.model_id, _TOKENIZER)

                tokenizer = Tokenizer.from_file(tokenizer_json)
                tokenizer.enable_truncation(max_length=_MAX_TOKENS)
                tokenizer.enable_padding()

                # One session, CPU only: this is a 133 MB encoder graph and the
                # provider list must stay explicit so onnxruntime does not warn
                # about absent CUDA on a CPU-only host.
                self._session = onnxruntime.InferenceSession(
                    weights, providers=["CPUExecutionProvider"]
                )
                self._tokenizer = tokenizer
            except Exception as exc:
                # Remember the failure so every later embed() sees the same
                # error instead of retrying a download that will fail again.
                self._load_error = exc
                raise

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._embed_sync, texts), timeout=EMBED_TIMEOUT_S
            )
        except TimeoutError as exc:
            raise RuntimeError(
                f"embedding timed out after {EMBED_TIMEOUT_S:.0f}s loading "
                f"{self.model_id!r}; the local ONNX runtime did not become ready"
            ) from exc

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        self._ensure_loaded()
        encodings = self._tokenizer.encode_batch(texts)
        feeds = self._build_feeds(encodings, np)
        last_hidden = self._session.run(None, feeds)[0]

        # CLS pooling, then L2-normalise so cosine similarity is a dot product.
        cls = last_hidden[:, 0]
        norms = np.linalg.norm(cls, axis=1, keepdims=True)
        vecs = cls / np.maximum(norms, 1e-12)

        if self._dim is None and len(vecs) > 0:
            self._dim = int(vecs.shape[1])
        return [v.tolist() for v in vecs.astype(np.float32)]

    def _build_feeds(self, encodings: list[Any], np: Any) -> dict[str, Any]:
        """Feed only the inputs this graph declares.

        bge graphs take ``input_ids`` + ``attention_mask``, and most also take
        ``token_type_ids``. Exporters differ on the third one, so match the
        session's own input names rather than assuming a fixed signature.
        """
        available = {i.name for i in self._session.get_inputs()}
        columns = {
            "input_ids": [e.ids for e in encodings],
            "attention_mask": [e.attention_mask for e in encodings],
            "token_type_ids": [e.type_ids for e in encodings],
        }
        return {
            name: np.asarray(values, dtype=np.int64)
            for name, values in columns.items()
            if name in available
        }
