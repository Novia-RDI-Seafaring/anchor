from __future__ import annotations

from pathlib import Path
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol, List, Dict

if TYPE_CHECKING:  # pragma: no cover
    from llama_index.core import StorageContext, VectorStoreIndex
    from .engine import LlamaIndexRag
    from llama_index.core.base.response.schema import RESPONSE_TYPE


class LlamaIndexStorageBackend(Protocol):
    """Internal storage strategy contract for LlamaIndex RAG implementations."""

    def get_storage_context(self, *, index_dir: Path, data_dir: Path, name: str) -> StorageContext: ...

    def create_storage_context(self, *, index_dir: Path, data_dir: Path, name: str) -> StorageContext: ...

    def save(self, *, vector_index: VectorStoreIndex, index_dir: Path, data_dir: Path) -> None: ...

    def add_toc(self, document_id: str, toc_items: List[Dict[str, Any]]) -> None: ...
    def get_toc(self, document_id: str) -> List[Dict[str, Any]]: ...
    def add_images(self, document_id: str, images: List[Dict[str, Any]]) -> None: ...
    def get_images(self, document_id: str) -> List[Dict[str, Any]]: ...
    def add_page_images(self, document_id: str, page_images: List[Dict[str, Any]]) -> None: ...
    def get_page_images(self, document_id: str, page_number: int) -> Dict[Any, Any]: ...
    def get_chunks_by_section(self, document_id: str, section_name: str) -> List[Dict[str, Any]]: ...


class LlamaIndexIngestionHandler(Protocol):
    """Internal ingestion strategy contract for LlamaIndex RAG implementations."""

    def ingest(
        self,
        rag: LlamaIndexRag,
        *,
        files: Sequence[Path | str] | None = None,
        max_files: int | None = None,
        **kwargs: Any,
    ) -> int: ...

class LlamaIndexQueryHandler(Protocol):
    """Internal query strategy contract for LlamaIndex RAG implementations."""

    def query(self, rag: LlamaIndexRag, question: str, **kwargs: Any) -> RESPONSE_TYPE: ...
