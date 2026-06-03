"""Embedding model selection shared by CLI and MCP service wiring."""
from __future__ import annotations

from anchor.extensions.anchor_pdfs.infra.llm.local_sentence_transformer_embedder import (
    LocalSentenceTransformerEmbedder,
)
from anchor.extensions.anchor_pdfs.infra.llm.openai_embedder import OpenAIEmbedder


def build_embedder(
    *,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LocalSentenceTransformerEmbedder | OpenAIEmbedder:
    """Build the embedder named by configuration.

    Local sentence-transformer models stay local even when an OpenAI key is
    present. OpenAI embeddings are selected only when the configured model id
    is an OpenAI embedding model.
    """
    if model.startswith("text-embedding-"):
        return OpenAIEmbedder(api_key=api_key, model=model, base_url=base_url)
    return LocalSentenceTransformerEmbedder(model=model)
