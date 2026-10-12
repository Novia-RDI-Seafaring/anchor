"""Embedder backed by onnxruntime — local, no API key, no torch.

Default model is ``hotchpotch/bekko-embedding-v1-a25m`` (384-d, multilingual,
190 MiB ONNX graph). The smaller ``hotchpotch/bekko-embedding-v1-a8m`` and
``BAAI/bge-small-en-v1.5`` remain supported local choices. Any
sentence-transformers repo that ships ``onnx/model.onnx`` works: the pooling
mode and maximum length are read from the repo's own ``1_Pooling/config.json``
and ``sentence_bert_config.json``, so bge pools the CLS token and bekko
mean-pools without a per-model table here.

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

DEFAULT_EMBED_MODEL = "hotchpotch/bekko-embedding-v1-a25m"

#: Cap on one embed call, including the first-call import + session build.
#: Loading numpy's native extension has been observed to wedge indefinitely
#: inside ``create_module`` in this process (0% CPU, never returns). A wedged
#: thread cannot be cancelled, so this does not rescue the worker — it returns
#: an honest failure to the caller instead of hanging the request until the
#: client's own timeout fires and leaves it guessing.
EMBED_TIMEOUT_S = 30.0

#: Repo-relative paths of the artefacts an ONNX embed needs. Mirrored by
#: ``_EMBED_ARTEFACTS`` in ``anchor.infra.models`` so prefetch caches them all.
_ONNX_WEIGHTS = "onnx/model.onnx"
_TOKENIZER = "tokenizer.json"
_POOLING_CONFIG = "1_Pooling/config.json"
_ST_CONFIG = "sentence_bert_config.json"

#: Published (pooling, max_seq_length) per model, used only when the configs
#: above are missing from an offline cache.
_KNOWN_CONFIGS = {"BAAI/bge-small-en-v1.5": ("cls", 512)}

#: Ceiling on tokens per text, below the model's own ``max_seq_length``. The
#: exported ONNX graphs use full attention, so memory grows with the square of
#: the length: one 8,192-token bekko input peaks near 5 GB, a 2,048-token one
#: near 250 MB. 2,048 still fits a whole spec table.
MAX_TOKENS_CAP = 2048

#: Batches are packed by padded length so one long region does not pad every
#: short one up to its size. A batch holds at most this many tokens of
#: attention, ``rows * length**2``: one text at the cap, or many short ones.
_ATTENTION_BUDGET = MAX_TOKENS_CAP**2
_MAX_BATCH = 32


class OnnxEmbedder:
    """Embed text with a sentence-transformers ONNX graph via onnxruntime.

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
        self._pooling = "cls"
        self.max_tokens = 512
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
                import json

                import onnxruntime
                from huggingface_hub import hf_hub_download
                from tokenizers import Tokenizer

                weights = hf_hub_download(self.model_id, _ONNX_WEIGHTS)
                tokenizer_json = hf_hub_download(self.model_id, _TOKENIZER)
                try:
                    with open(hf_hub_download(self.model_id, _POOLING_CONFIG)) as f:
                        pooling = _pooling_mode(json.load(f))
                    with open(hf_hub_download(self.model_id, _ST_CONFIG)) as f:
                        max_seq = int(json.load(f).get("max_seq_length") or 512)
                except Exception:
                    # An offline cache prefetched before these configs were
                    # read holds only the graph + tokenizer. Known models
                    # fall back to their published settings; anything else
                    # must not guess its pooling.
                    if self.model_id not in _KNOWN_CONFIGS:
                        raise
                    pooling, max_seq = _KNOWN_CONFIGS[self.model_id]

                self._pooling = pooling
                self.max_tokens = min(max_seq, MAX_TOKENS_CAP)
                tokenizer = Tokenizer.from_file(tokenizer_json)
                tokenizer.enable_truncation(max_length=self.max_tokens)
                tokenizer.enable_padding()

                # One session, CPU only: this is a ~130 MB encoder graph and the
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
        # A lone encode is never padded, so these are the true lengths.
        lengths = [len(self._tokenizer.encode(t).ids) for t in texts]
        out: list[Any] = [None] * len(texts)
        for batch in _length_batches(lengths):
            encodings = self._tokenizer.encode_batch([texts[i] for i in batch])
            vecs = self._embed_encodings(encodings, np)
            for i, vec in zip(batch, vecs, strict=True):
                out[i] = vec

        if self._dim is None and out:
            self._dim = len(out[0])
        return out

    def _embed_encodings(self, encodings: list[Any], np: Any) -> list[list[float]]:
        """Run one padded batch, pool it, and L2-normalise each row."""
        feeds = self._build_feeds(encodings, np)
        last_hidden = self._session.run(None, feeds)[0]

        if self._pooling == "mean":
            mask = feeds["attention_mask"][..., None].astype(np.float32)
            pooled = (last_hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
        else:
            pooled = last_hidden[:, 0]
        # L2-normalise so cosine similarity is a dot product.
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        vecs = pooled / np.maximum(norms, 1e-12)
        return [v.tolist() for v in vecs.astype(np.float32)]

    def _build_feeds(self, encodings: list[Any], np: Any) -> dict[str, Any]:
        """Feed only the inputs this graph declares.

        bge graphs take ``input_ids`` + ``attention_mask``, and most also take
        ``token_type_ids``; ModernBERT graphs such as bekko take only the first
        two. Match the session's own input names rather than assuming a fixed
        signature.
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


def _pooling_mode(config: dict[str, Any]) -> str:
    """The pooling a sentence-transformers ``1_Pooling/config.json`` asks for.

    Only CLS and mean are implemented. Anything else raises, because pooling
    the wrong way yields vectors that look fine and rank badly.
    """
    if config.get("pooling_mode_cls_token"):
        return "cls"
    if config.get("pooling_mode_mean_tokens"):
        return "mean"
    raise ValueError(f"unsupported pooling config: {config}")


def _length_batches(lengths: list[int]) -> list[list[int]]:
    """Group text indexes by length so each batch stays within the budget.

    Sorting by length keeps padding small; a batch closes when one more row
    would push ``rows * longest**2`` past :data:`_ATTENTION_BUDGET`.
    """
    order = sorted(range(len(lengths)), key=lambda i: lengths[i])
    batches: list[list[int]] = []
    current: list[int] = []
    for i in order:
        rows = len(current) + 1
        if current and (rows > _MAX_BATCH or rows * lengths[i] ** 2 > _ATTENTION_BUDGET):
            batches.append(current)
            current = []
        current.append(i)
    if current:
        batches.append(current)
    return batches
