"""Embedding model selection shared by CLI and MCP service wiring."""
from __future__ import annotations

from anchor.extensions.anchor_pdfs.infra.llm.onnx_bge_embedder import OnnxBgeEmbedder
from anchor.extensions.anchor_pdfs.infra.llm.openai_embedder import OpenAIEmbedder
from anchor.infra.egress_policy import EgressPolicyError, is_remote_embedding_model


def build_embedder(
    *,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
) -> OnnxBgeEmbedder | OpenAIEmbedder:
    """Build the embedder named by configuration.

    Local models run on onnxruntime and stay local even when an OpenAI key is
    present. OpenAI embeddings are selected only when the configured model id
    is an OpenAI embedding model.

    A remote embedder is only ever constructed from an explicit,
    policy-approved credential. Without one, the underlying OpenAI client
    would fall back to an ambient ``OPENAI_API_KEY`` and silently send
    document text off-host from a no-egress (``local_only``) environment
    (#271), so construction refuses instead of building the client.
    """
    if is_remote_embedding_model(model):
        if api_key is None:
            raise EgressPolicyError(
                f"embed_model {model!r} is a remote embedding model but this "
                "environment resolved no approved model credential; set "
                "embed_model to a local model (for example "
                "'BAAI/bge-small-en-v1.5') or configure the environment's "
                "provider credential"
            )
        return OpenAIEmbedder(api_key=api_key, model=model, base_url=base_url)
    return OnnxBgeEmbedder(model=model)
