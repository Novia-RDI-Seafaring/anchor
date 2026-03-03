from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from ..kb_engine.engine import LlamaIndexRag
from ..kb_engine.pgvector import PgVectorStorageBackend
from ..kb_engine.rich_docling import RichDoclingIngestionHandler
# Use KETJU's query handler since we haven't modified it
from ketju.rag.llama_index.query.simple import SimpleLlamaIndexQueryHandler

from llama_index.core import Settings
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.llms.azure_openai import AzureOpenAI

from ..core.config import get_settings


def _env(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or normalized.lower() in {"none", "null"}:
        return None
    return normalized


# Ensure provider credentials from backend/.env are available to os.getenv lookups.
load_dotenv(override=False)

def configure_llama_index(model_name: Optional[str] = None, provider: Optional[str] = None):
    """Configure global LlamaIndex settings from environment or provided values."""
    config = get_settings()

    requested_provider = (provider or os.getenv("DEFAULT_PROVIDER") or "").strip().lower()

    azure_key = _env(os.getenv("AZURE_OPENAI_API_KEY"))
    azure_endpoint = _env(os.getenv("AZURE_OPENAI_ENDPOINT"))
    azure_deployment = _env(os.getenv("AZURE_OPENAI_DEPLOYMENT"))
    azure_embed_deployment = _env(model_name) or _env(os.getenv("AZURE_EMBEDDING_DEPLOYMENT"))
    openai_key = _env(os.getenv("OPENAI_API_KEY"))

    if requested_provider:
        effective_provider = requested_provider
    elif azure_key and azure_endpoint:
        effective_provider = "azure"
    elif openai_key:
        effective_provider = "openai"
    else:
        effective_provider = "ollama"

    if effective_provider == "azure" and not (azure_key and azure_endpoint):
        if openai_key:
            effective_provider = "openai"
        else:
            raise ValueError("Azure embedding provider selected but AZURE_OPENAI_API_KEY/AZURE_OPENAI_ENDPOINT are missing.")

    if effective_provider == "openai" and not openai_key:
        if azure_key and azure_endpoint:
            effective_provider = "azure"
        else:
            raise ValueError("OpenAI embedding provider selected but OPENAI_API_KEY is missing.")

    if effective_provider == "azure":
        api_version = _env(os.getenv("OPENAI_API_VERSION")) or "2024-12-01-preview"

        Settings.llm = AzureOpenAI(
            model=azure_deployment or "gpt-4o",
            deployment_name=azure_deployment,
            api_key=azure_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )

        azure_model = "text-embedding-3-large"
        if azure_embed_deployment:
            lowered = azure_embed_deployment.lower()
            if "3-small" in lowered:
                azure_model = "text-embedding-3-small"
            elif "ada-002" in lowered:
                azure_model = "text-embedding-ada-002"

        embed_kwargs = {
            "model": azure_model,
            "deployment_name": azure_embed_deployment or azure_model,
            "api_key": azure_key,
            "azure_endpoint": azure_endpoint,
            "api_version": api_version,
        }
        if azure_model.startswith("text-embedding-3"):
            embed_kwargs["dimensions"] = config.embedding_dimension

        Settings.embed_model = AzureOpenAIEmbedding(**embed_kwargs)
    elif effective_provider == "ollama":
        from llama_index.llms.ollama import Ollama
        from llama_index.embeddings.ollama import OllamaEmbedding

        ollama_url = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
        Settings.llm = Ollama(model=os.getenv("LLM_MODEL", "llama3.2"), base_url=ollama_url)
        embedding_model = _env(model_name) or _env(os.getenv("OLLAMA_EMBEDDING_MODEL")) or "nomic-embed-text"
        if embedding_model.startswith("ollama:"):
            embedding_model = embedding_model.split(":", 1)[1]
        Settings.embed_model = OllamaEmbedding(
            model_name=embedding_model,
            base_url=ollama_url
        )
    else:
        selected_embedding_model = _env(model_name) or "text-embedding-3-small"
        Settings.llm = OpenAI(model=os.getenv("LLM_MODEL", "gpt-4o-mini"), api_key=openai_key)

        embed_kwargs = {
            "model": selected_embedding_model,
            "api_key": openai_key,
        }
        if selected_embedding_model.startswith("text-embedding-3"):
            embed_kwargs["dimensions"] = config.embedding_dimension

        Settings.embed_model = OpenAIEmbedding(**embed_kwargs)

# Call configuration on import
configure_llama_index()

def get_ketju_rag(
    collection_name: Optional[str] = None,
    preserve_images: bool = True,
    preserve_tables: bool = True,
    enable_ocr: bool = False,
    table_mode: str = "fast"
) -> LlamaIndexRag:
    """
    Get a KETJU RAG instance configured with ANCHOR's settings.
    """
    configure_llama_index()

    settings = get_settings()
    
    # Use ANCHOR's settings for KETJU's PgVectorStorageBackend
    storage_backend = PgVectorStorageBackend(
        database_url=settings.database_url,
        table_name=collection_name or f"ketju_{settings.vector_db_collection}",
        schema_name=settings.db_schema,
        embed_dim=settings.embedding_dimension
    )
    
    # Use our new RichDoclingIngestionHandler
    ingestion_handler = RichDoclingIngestionHandler(
        preserve_images=preserve_images,
        preserve_tables=preserve_tables,
        enable_ocr=enable_ocr,
        table_mode=table_mode
    )
    
    # Simple query handler for now
    query_handler = SimpleLlamaIndexQueryHandler()
    
    return LlamaIndexRag(
        name="anchor_ketju_rag",
        docs_dir=Path(settings.uploads_dir),
        storage_backend=storage_backend,
        ingestion_handler=ingestion_handler,
        query_handler=query_handler,
        embedding_model="text-embedding-3-small" # Match KETJU default/ANCHOR dimension
    )
