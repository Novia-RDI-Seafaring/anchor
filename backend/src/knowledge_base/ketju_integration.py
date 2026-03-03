from __future__ import annotations

from pathlib import Path
from typing import Optional

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

def configure_llama_index(model_name: Optional[str] = None, provider: Optional[str] = None):
    """Configure global LlamaIndex settings from environment or provided values."""
    config = get_settings()
    
    # Provider selection
    provider = (provider or os.getenv("DEFAULT_PROVIDER") or "azure").lower()
    
    if provider == "azure":
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        azure_embed_deployment = model_name or os.getenv("AZURE_EMBEDDING_DEPLOYMENT")
        api_version = os.getenv("OPENAI_API_VERSION", "2024-12-01-preview")
        
        if azure_key and azure_endpoint:
            Settings.llm = AzureOpenAI(
                model=azure_deployment or "gpt-4o",
                deployment_name=azure_deployment,
                api_key=azure_key,
                azure_endpoint=azure_endpoint,
                api_version=api_version,
            )
            # Map deployment name to standard OpenAI model type for LlamaIndex
            azure_model = "text-embedding-3-large"
            if azure_embed_deployment:
                if "3-small" in azure_embed_deployment.lower():
                    azure_model = "text-embedding-3-small"
                elif "ada-002" in azure_embed_deployment.lower():
                    azure_model = "text-embedding-ada-002"

            Settings.embed_model = AzureOpenAIEmbedding(
                model=azure_model,
                deployment_name=azure_embed_deployment or azure_model,
                api_key=azure_key,
                azure_endpoint=azure_endpoint,
                api_version=api_version,
                dimensions=config.embedding_dimension,
            )
    elif provider == "ollama":
        from llama_index.llms.ollama import Ollama
        from llama_index.embeddings.ollama import OllamaEmbedding
        
        ollama_url = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
        Settings.llm = Ollama(model=os.getenv("LLM_MODEL", "llama3.2"), base_url=ollama_url)
        Settings.embed_model = OllamaEmbedding(
            model_name=model_name or os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
            base_url=ollama_url
        )
    else:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key == "None":
            openai_key = None
            
        if openai_key:
            Settings.llm = OpenAI(model="gpt-4o-mini", api_key=openai_key)
            Settings.embed_model = OpenAIEmbedding(
                model=model_name or "text-embedding-3-small", 
                api_key=openai_key,
                dimensions=config.embedding_dimension,
            )

# Call configuration on import
import os
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
