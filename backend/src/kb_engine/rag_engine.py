import os
from logging import getLogger
from pathlib import Path
from typing import Any, Sequence

from ketju.rag.llama_index.variants.anchor import AnchorDoclingRag
from ketju.rag.llama_index.storage.pgvector import PgVectorStorageBackend

from .query import QueryHandler
from src.core.config import get_settings

logger = getLogger(__name__)


class RagEngine(AnchorDoclingRag):
    """Anchor-KB RAG engine — extends AnchorDoclingRag with file tracking."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.ingested_files: set[str] = set()

    def _ingest(
        self,
        files: Sequence[Path | str] | None = None,
        max_files: int | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> int:
        ingested = super()._ingest(files=files, max_files=max_files, document_ids=document_ids)
        for f in self.resolve_pdf_files(files=files, max_files=max_files):
            self.ingested_files.add(str(f))
        return ingested

    def resolve_pdf_files(
        self,
        files: Sequence[Path | str] | None = None,
        max_files: int | None = None,
    ) -> list[Path]:
        if files:
            resolved = [Path(f) for f in files if str(f).endswith(".pdf")]
        elif self.docs_dir and self.docs_dir.exists():
            resolved = list(self.docs_dir.glob("**/*.pdf"))
        else:
            resolved = []
        if max_files is not None:
            resolved = resolved[:max_files]
        return resolved


_rag_engine: RagEngine | None = None


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
        embedding_dim = 3072  # existing pgvector table uses vector(3072)
        Settings.embed_model = OpenAIEmbedding(model=embedding_model_id)
        Settings.llm = OpenAI(model="gpt-4o-mini")

        storage_backend = PgVectorStorageBackend(
            database_url=settings.database_url,
            table_name=settings.ketju_table_name,
            schema_name=settings.ketju_schema_name,
            embed_dim=embedding_dim,
        )
        # pgvector HNSW cannot index vectors above 2000 dimensions
        if embedding_dim > 2000:
            storage_backend.hnsw_kwargs = None

        enrich = os.getenv("ENRICH_CHAPTER_METADATA", "false").lower() == "true"

        _rag_engine = RagEngine(
            name="anchor_rag5",
            persist_dir=persist_dir,
            embedding_model=embedding_model_id,
            storage_backend=storage_backend,
            enrich_metadata=enrich,
            query_handler=QueryHandler(),
        )
    return _rag_engine

