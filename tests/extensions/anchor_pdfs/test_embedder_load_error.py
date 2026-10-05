"""The ONNX embedder loads lazily, and a failed load surfaces from ``embed()``.

Construction must not build the session or start a thread. The predecessor
imported ``sentence_transformers`` (torch + transformers + scipy + sklearn)
and warmed it in a daemon thread, which deadlocked inside ``create_module``:
two such threads wedged on CPython's import lock versus the Windows loader
lock and hung the MCP handshake, and moving the import to first-embed simply
moved the hang into ``search_documents``. onnxruntime removes the cost rather
than rescheduling it, so laziness here is just tidiness.

The load error is still cached, so a broken model id fails the same way every
call instead of re-downloading (this is what #237 was about: an unhandled
exception escaping a background load aborted the interpreter at teardown).
"""
from __future__ import annotations

import threading

import pytest

from anchor.extensions.anchor_pdfs.infra.llm.onnx_bge_embedder import OnnxBgeEmbedder


def _install_failing_session(monkeypatch):
    """Make session construction raise, as an unreachable hub would."""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("hub unreachable")

    monkeypatch.setattr(OnnxBgeEmbedder, "_ensure_loaded", _boom)


def test_construction_neither_loads_nor_starts_a_thread():
    before = set(threading.enumerate())

    emb = OnnxBgeEmbedder("nonexistent/model")

    assert set(threading.enumerate()) == before
    assert emb._session is None
    assert emb._load_error is None
    assert emb.dim is None


def test_model_id_is_recorded_for_embeddings_metadata():
    assert OnnxBgeEmbedder("some/model").model_id == "some/model"


@pytest.mark.asyncio
async def test_embed_of_nothing_never_touches_the_model():
    emb = OnnxBgeEmbedder("nonexistent/model")

    assert await emb.embed([]) == []
    assert emb._session is None


@pytest.mark.asyncio
async def test_embed_reraises_the_load_error(monkeypatch):
    _install_failing_session(monkeypatch)
    emb = OnnxBgeEmbedder("nonexistent/model")

    with pytest.raises(RuntimeError, match="hub unreachable"):
        await emb.embed(["anything"])
