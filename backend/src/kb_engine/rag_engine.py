from pathlib import Path
from ketju.rag.llama_index.variants.simple import LlamaIndexRag
from ketju.rag.llama_index.storage.pgvector import PgVectorStorageBackend
from .ingest import IngestionHandler
from .query import QueryHandler
from logging import getLogger
from src.core.config import get_settings
logger = getLogger(__name__)
import os
from typing import Any, Sequence


class RagEngine(LlamaIndexRag):
    ingested_files: set[str]
    def __init__(
        self,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.ingested_files = set()

    def _ingest(
        self,
        files: Sequence[Path | str] | None = None,
        max_files: int | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> int:
        ingested = self.ingestion_handler.ingest(
            self,
            files=files,
            max_files=max_files,
            document_ids=document_ids,
        )
        resolved_files = self.resolve_pdf_files(files=files, max_files=max_files)
        for file in resolved_files:
            self.ingested_files.add(str(file))
        return ingested
    
    @property
    def docstore(self) -> 'BaseDocumentStore':
        return self.vector_index.storage_context.docstore

    def get_document(self, document_id: str):
        retirever = self.vector_index.as_retriever()
        from llama_index.core.storage.storage_context import StorageContext
        from llama_index.core.storage.docstore import BaseDocumentStore
        storage_context:StorageContext = self.vector_index.storage_context
        docstore:BaseDocumentStore = storage_context.docstore
        doc = docstore.get_document(document_id)

    def resolve_pdf_files(
        self,
        files: Sequence[Path | str] | None = None,
        max_files: int | None = None,
    ) -> list[Path]:
        # Simple resolution logic
        if files:
            resolved = [Path(f) for f in files if str(f).endswith(".pdf")]
        elif self.docs_dir and self.docs_dir.exists():
            resolved = list(self.docs_dir.glob("**/*.pdf"))
        else:
            resolved = []
            
        if max_files is not None:
            resolved = resolved[:max_files]
        return resolved



_rag_engine = None

def get_rag_engine() -> RagEngine: 
    global _rag_engine
    if _rag_engine is None:
        from llama_index.core import Settings
        from llama_index.embeddings.openai import OpenAIEmbedding
        from llama_index.llms.openai import OpenAI

        settings = get_settings()

        persist_dir = settings.rag_workspace_dir
        persist_dir.mkdir(parents=True, exist_ok=True)

        embedding_model_id = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
        # Existing pgvector table uses vector(3072), runtime embeddings must match.
        embedding_dim = 3072
        Settings.embed_model = OpenAIEmbedding(model=embedding_model_id)
        Settings.llm = OpenAI(model="gpt-4o-mini")

        storage_backend = PgVectorStorageBackend(
            database_url=settings.database_url,
            table_name=settings.ketju_table_name,
            schema_name=settings.ketju_schema_name,
            embed_dim=embedding_dim,
        )
        # pgvector HNSW cannot index vectors above 2000 dimensions.
        if embedding_dim > 2000:
            storage_backend.hnsw_kwargs = None

        _rag_engine = RagEngine(
            name="anchor_rag5",
            persist_dir=persist_dir,
            query_handler=QueryHandler(),
            ingestion_handler=IngestionHandler(),
            embedding_model=embedding_model_id,
            storage_backend=storage_backend,
        )
    return _rag_engine

