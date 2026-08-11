"""Regression for #237: the embedder's eager preload thread must not leak.

``LocalSentenceTransformerEmbedder`` warms the model in a daemon thread on
construction. If that load fails (e.g. a HuggingFace download error on CI), the
exception must be captured, not left unhandled in the background thread — an
unhandled thread exception aborts the interpreter at teardown with exit code
134. The error must instead surface from ``embed()`` where a caller can handle
it.
"""
from __future__ import annotations

import sys
import threading
import types

import pytest

from anchor.extensions.anchor_pdfs.infra.llm.local_sentence_transformer_embedder import (
    LocalSentenceTransformerEmbedder,
)


def _install_failing_sentence_transformers(monkeypatch):
    """Fake sentence_transformers whose SentenceTransformer(...) always raises."""
    fake = types.ModuleType("sentence_transformers")

    class _BoomSentenceTransformer:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("hub unreachable")

    fake.SentenceTransformer = _BoomSentenceTransformer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)


def test_preload_failure_is_captured_not_leaked(monkeypatch):
    _install_failing_sentence_transformers(monkeypatch)

    # Constructing must not raise even though the eager load fails.
    emb = LocalSentenceTransformerEmbedder("nonexistent/model")

    # The daemon preload thread must finish without an unhandled exception.
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon:
            t.join(timeout=5)

    assert emb._load_error is not None
    assert isinstance(emb._load_error, RuntimeError)


@pytest.mark.asyncio
async def test_embed_reraises_the_load_error(monkeypatch):
    _install_failing_sentence_transformers(monkeypatch)
    emb = LocalSentenceTransformerEmbedder("nonexistent/model")

    with pytest.raises(RuntimeError, match="hub unreachable"):
        await emb.embed(["anything"])
