from ketju.rag.llama_index.variants.simple_docling_full_ctx import SimpleDoclingFullCtxRag
from ketju.rag.base import BaseRAG
from pathlib import Path

from llama_index.core import VectorStoreIndex, get_response_synthesizer
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.base.response.schema import RESPONSE_TYPE
from ketju.rag.llama_index.variants.simple import LlamaIndexRag
from ketju.rag.llama_index.storage.pgvector import PgVectorStorageBackend
from .ingest import IngestionHandler
from .pgvector import StorageBackend
from .query import QueryHandler
from logging import getLogger
logger = getLogger(__name__)
import os
from typing import Dict, Any, List, Sequence
from .query import QueryHandler


class RagEngine(LlamaIndexRag):
    ingested_files: set[str]
    def __init__(
        self,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        print(f"RagEngine initialized with and kwargs: {kwargs}")
        self.ingested_files = set()

    def _ingest(
        self,
        files: Sequence[Path | str] | None = None,
        max_files: int | None = None,
    ) -> int:
        l = super()._ingest(files=files, max_files=max_files)
        for f in files[:max_files] if files else [] : self.ingested_files.add(str(f))
        return l
    
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

    def list_documents(self) -> list[str]:
        return list(self.ingested_files)
    
    def list_document_toc(self, document_id: str):
        return "the answer is 43"
   

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
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # stting sform llam index
            from llama_index.core import Settings
            from llama_index.embeddings.openai import OpenAIEmbedding
            from llama_index.llms.openai import OpenAI
            Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-large")
            Settings.llm = OpenAI(model="gpt-4o-mini")
            db_url = f"postgresql://{os.getenv('PGVECTOR_USER')}:{os.getenv('PGVECTOR_PASSWORD')}@{os.getenv('PGVECTOR_HOST')}:{os.getenv('PGVECTOR_PORT')}/{os.getenv('PGVECTOR_DB')}"
            _rag_engine = RagEngine(
                name="anchor_rag5",
                persist_dir=Path(tmpdir),
                query_handler=QueryHandler(),
                ingestion_handler=IngestionHandler(),
                embedding_model="text-embedding-3-large",
                storage_backend=PgVectorStorageBackend(database_url=db_url, embed_dim=3072),
            )
    return _rag_engine

