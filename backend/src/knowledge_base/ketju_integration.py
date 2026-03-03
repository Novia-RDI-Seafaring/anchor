from __future__ import annotations

from pathlib import Path
from typing import Optional

from .kb_engine.engine import LlamaIndexRag
from .kb_engine.pgvector import PgVectorStorageBackend
from .kb_engine.rich_docling import RichDoclingIngestionHandler
# Use KETJU's query handler since we haven't modified it
from ketju.rag.llama_index.query.simple import SimpleLlamaIndexQueryHandler

from ..core.config import get_settings

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
