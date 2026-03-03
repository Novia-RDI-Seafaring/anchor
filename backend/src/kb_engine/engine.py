from __future__ import annotations

from pathlib import Path
from collections.abc import Sequence
from typing import Optional, Any, TYPE_CHECKING

from .contracts import LlamaIndexStorageBackend, LlamaIndexIngestionHandler, LlamaIndexQueryHandler

if TYPE_CHECKING:
    from llama_index.core import StorageContext, VectorStoreIndex
    from llama_index.core.schema import Node
    from llama_index.core.storage.docstore.types import BaseDocumentStore
    from llama_index.core.vector_stores.types import BasePydanticVectorStore

try:
    from llama_index.core import Settings, StorageContext, VectorStoreIndex
    from llama_index.core.schema import Node
    from llama_index.core.storage.docstore.types import BaseDocumentStore
    from llama_index.core.vector_stores.types import BasePydanticVectorStore
except ImportError:
    pass

class LlamaIndexRag:
    """
    Local RAG engine for ANCHOR, coordinating storage, ingestion, and querying.
    """
    def __init__(self,
        name: str = "anchor_rag",
        *,
        docs_dir: Path | None = None,
        embedding_model: str = "text-embedding-3-small",
        storage_backend: LlamaIndexStorageBackend | None = None,
        ingestion_handler: LlamaIndexIngestionHandler | None = None,
        query_handler: LlamaIndexQueryHandler | None = None,
        ) -> None:
        self.name = name
        self.docs_dir = docs_dir
        self.embedding_model = embedding_model
        
        self.storage_backend = storage_backend
        self.ingestion_handler = ingestion_handler
        self.query_handler = query_handler
        
        # Initialize index
        self._index_dir = Path("indices") / name
        self._data_dir = Path("data") / name
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self.vector_store_index = self._setup_index(
            storage_context=self.storage_backend.get_storage_context(
                index_dir=self._index_dir,
                data_dir=self._data_dir,
                name="default",
            )
        )

    def _setup_index(self, storage_context: Optional[StorageContext] = None, nodes: list[Node] | None = None):
        _nodes = nodes or []
        if _nodes:
            return VectorStoreIndex(_nodes, storage_context=storage_context, embed_model=Settings.embed_model)
        return VectorStoreIndex(
            [],
            storage_context=storage_context,
            embed_model=Settings.embed_model,
        )

    @property
    def vector_index(self) -> VectorStoreIndex:
        return self.vector_store_index

    @property
    def docstore(self) -> BaseDocumentStore:
        return self.vector_index.storage_context.docstore

    @property
    def vector_store(self) -> BasePydanticVectorStore:
        return self.vector_index.vector_store

    def ingest(
        self,
        files: Sequence[Path | str] | None = None,
        max_files: int | None = None,
        **kwargs: Any,
    ) -> int:
        return self.ingestion_handler.ingest(self, files=files, max_files=max_files, **kwargs)

    def save(self) -> None:
        self.storage_backend.save(
            vector_index=self.vector_index,
            index_dir=self._index_dir,
            data_dir=self._data_dir,
        )

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
