"""Construction-time egress guard in embedder selection (#271).

A remote embedding client falls back to the ambient ``OPENAI_API_KEY`` when
built without an explicit key, so a ``local_only`` environment that (mis)claims
a ``text-embedding-*`` embed_model would silently send document text off-host.
``build_embedder`` must therefore refuse to construct the remote client at all
unless a policy-approved credential is passed in.
"""
from __future__ import annotations

import pytest

from anchor.extensions.anchor_pdfs.infra.llm import embedder_selection
from anchor.extensions.anchor_pdfs.infra.llm.embedder_selection import build_embedder
from anchor.infra.egress_policy import EgressPolicyError


class _SpyEmbedder:
    """Stands in for a real embedder class and records constructions."""

    constructed: list[dict] = []

    def __init__(self, *args, **kwargs):
        type(self).constructed.append({"args": args, "kwargs": kwargs})


@pytest.fixture
def spies(monkeypatch):
    class RemoteSpy(_SpyEmbedder):
        constructed = []

    class LocalSpy(_SpyEmbedder):
        constructed = []

    monkeypatch.setattr(embedder_selection, "OpenAIEmbedder", RemoteSpy)
    monkeypatch.setattr(embedder_selection, "LocalSentenceTransformerEmbedder", LocalSpy)
    return RemoteSpy, LocalSpy


def test_remote_model_without_credential_never_constructs_remote_client(
    spies, monkeypatch
):
    remote_spy, local_spy = spies
    # An ambient key is exactly what must NOT be picked up.
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-public-key")

    with pytest.raises(EgressPolicyError, match="embed_model"):
        build_embedder(model="text-embedding-3-small", api_key=None, base_url=None)

    assert remote_spy.constructed == []
    assert local_spy.constructed == []


def test_remote_model_with_explicit_credential_builds_remote_client(spies):
    remote_spy, _local_spy = spies

    embedder = build_embedder(
        model="text-embedding-3-small",
        api_key="approved-key",
        base_url="https://models.example/v1",
    )

    assert isinstance(embedder, remote_spy)
    assert remote_spy.constructed == [
        {
            "args": (),
            "kwargs": {
                "api_key": "approved-key",
                "model": "text-embedding-3-small",
                "base_url": "https://models.example/v1",
            },
        }
    ]


def test_local_model_stays_local_even_with_credential(spies):
    remote_spy, local_spy = spies

    embedder = build_embedder(
        model="BAAI/bge-small-en-v1.5",
        api_key="approved-key",
        base_url="https://models.example/v1",
    )

    assert isinstance(embedder, local_spy)
    assert remote_spy.constructed == []
