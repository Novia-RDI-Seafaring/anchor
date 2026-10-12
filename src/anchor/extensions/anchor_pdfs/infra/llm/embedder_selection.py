"""Embedding model selection shared by CLI and MCP service wiring."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from anchor.extensions.anchor_pdfs.infra.llm.onnx_bge_embedder import OnnxBgeEmbedder
from anchor.extensions.anchor_pdfs.infra.llm.openai_embedder import OpenAIEmbedder
from anchor.infra.egress_policy import (
    EgressPolicyError,
    MissingModelCredentialError,
    is_remote_embedding_model,
)

if TYPE_CHECKING:
    from anchor.infra.egress_policy import EgressPolicy


class MissingCredentialEmbedder:
    """Stand-in for a remote embedder whose key is not visible yet.

    It builds no client and sends nothing. Construction succeeds so read-only
    operations (status, listing, reading regions, canvas work) keep working;
    the first call that really needs the remote model raises a structured
    :class:`MissingModelCredentialError` naming where the key goes.
    """

    def __init__(self, model: str, *, dotenv_path: Path | None = None) -> None:
        self.model_id = model
        self._dotenv_path = dotenv_path

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise MissingModelCredentialError(self.model_id, dotenv_path=self._dotenv_path)


def build_project_embedder(
    *, model: str, policy: EgressPolicy
) -> OnnxBgeEmbedder | OpenAIEmbedder | MissingCredentialEmbedder:
    """Build a project's embedder, deferring a missing remote credential.

    The policy has already rejected a remote model in a no-egress environment,
    so the only deferred case is an egress-capable environment whose key is
    not visible to this process.
    """
    if (
        is_remote_embedding_model(model)
        and policy.server_egress_allowed
        and not policy.remote_clients_enabled
    ):
        return MissingCredentialEmbedder(model, dotenv_path=policy.dotenv_path)
    return build_embedder(model=model, api_key=policy.api_key, base_url=policy.base_url)


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
