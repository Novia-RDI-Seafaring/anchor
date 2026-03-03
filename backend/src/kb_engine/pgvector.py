"""Postgres/pgvector storage backend for ANCHOR KB.
Localized from KETJU to allow project-specific extensions without modifying external library.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List
import json

from .contracts import LlamaIndexStorageBackend


class PgVectorStorageBackend(LlamaIndexStorageBackend):
    """Storage strategy using Postgres + pgvector + postgres doc/index stores."""

    def __init__(
        self,
        *,
        database_url: str | None = None,
        table_name: str = "kb_vectors",
        schema_name: str = "public",
        embed_dim: int | None = None,
        hybrid_search: bool = False,
        text_search_config: str | None = None,
        hnsw_kwargs: dict[str, Any] | None = None,
    ) -> None:
        from sqlalchemy import create_engine, make_url
        self._storage_contexts: Dict[str, Any] = {}
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL is required (or pass database_url=...).")

        self.table_name = table_name
        self.schema_name = schema_name
        self.embed_dim = embed_dim
        self.hybrid_search = hybrid_search
        self.text_search_config = text_search_config
        self.hnsw_kwargs = hnsw_kwargs or {
            "hnsw_m": 16,
            "hnsw_ef_construction": 64,
            "hnsw_ef_search": 40,
            "hnsw_dist_method": "vector_cosine_ops",
        }
        
        # Persistent engine for sync operations (TOC, Images, etc.)
        self._engine = create_engine(self.database_url, pool_size=5, max_overflow=10)
        self._url = make_url(self.database_url)

    def _db_url(self):
        from sqlalchemy import make_url  # type: ignore

        return make_url(self.database_url or "")

    def _get_vector_store(self) -> Any:
        from llama_index.vector_stores.postgres import PGVectorStore  # type: ignore
        from llama_index.core import Settings  # type: ignore

        url = self._url

        dim = self.embed_dim
        if dim is None:
            dim = getattr(Settings.embed_model, "embed_dim", None)
        if dim is None:
            raise ValueError(
                "Embedding dimension is unknown. Pass embed_dim=... when constructing PgVectorStorageBackend."
            )

        params: dict[str, Any] = {
            "database": url.database or "postgres",
            "host": url.host or "localhost",
            "password": url.password or "",
            "port": url.port or 5432,
            "user": url.username or "postgres",
            "table_name": self.table_name,
            "schema_name": self.schema_name,
            "embed_dim": int(dim),
            "hybrid_search": self.hybrid_search,
            "hnsw_kwargs": self.hnsw_kwargs,
        }
        if self.text_search_config is not None:
            params["text_search_config"] = self.text_search_config

        return PGVectorStore.from_params(**params)  # type: ignore

    def _get_docstore(self) -> Any:
        from llama_index.storage.docstore.postgres import PostgresDocumentStore  # type: ignore
        db_url = self.database_url
        return PostgresDocumentStore.from_uri(  # type: ignore
            uri=db_url,
            table_name=f"{self.table_name}_docstore",
            schema_name=self.schema_name,
        )

    def _get_index_store(self) -> Any:
        from llama_index.storage.index_store.postgres import PostgresIndexStore  # type: ignore
        db_url = self.database_url
        return PostgresIndexStore.from_uri(  # type: ignore
            uri=db_url,
            table_name=f"{self.table_name}_indexstore",
            schema_name=self.schema_name,
        )

    def _get_graph_store(self) -> Any:
        from llama_index.core.graph_stores.simple import SimpleGraphStore  # type: ignore
        return SimpleGraphStore()

    def _get_property_graph_store(self) -> Any:
        from llama_index.core.graph_stores.simple_labelled import SimplePropertyGraphStore  # type: ignore
        return SimplePropertyGraphStore()

    def create_storage_context(self, *, index_dir: Path, data_dir: Path, name: str) -> Any:
        from llama_index.core import StorageContext  # type: ignore
        return StorageContext.from_defaults(
            vector_store=self._get_vector_store(),
            index_store=self._get_index_store(),
            docstore=self._get_docstore(),
            graph_store=self._get_graph_store(),
            property_graph_store=self._get_property_graph_store(),
        )

    def get_storage_context(self, *, index_dir: Path, data_dir: Path, name: str) -> Any:
        if name in self._storage_contexts:
            return self._storage_contexts[name]
        storage_context = self.create_storage_context(index_dir=index_dir, data_dir=data_dir, name=name)
        self._storage_contexts[name] = storage_context
        return storage_context

    def save(self, *, vector_index: Any, index_dir: Path, data_dir: Path) -> None:
        return

    def _ensure_rich_tables(self) -> None:
        """Create TOC and Images tables if they don't exist, matching ANCHOR schema."""
        from sqlalchemy import text  # type: ignore

        with self._engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {self.schema_name}.document_toc (
                    document_id TEXT PRIMARY KEY,
                    toc_json JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {self.schema_name}.document_images (
                    id SERIAL PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    image_type TEXT,
                    page_number INTEGER,
                    image_base64 TEXT,
                    caption TEXT,
                    alt_text TEXT,
                    bbox JSONB,
                    width INTEGER,
                    height INTEGER,
                    metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {self.schema_name}.page_images (
                    id SERIAL PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    image_base64 TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(document_id, page_number)
                );
            """))
            conn.commit()

    def add_toc(self, document_id: str, toc_items: list[dict[str, Any]]) -> None:
        self._ensure_rich_tables()
        from sqlalchemy import text  # type: ignore
        with self._engine.connect() as conn:
            conn.execute(text(f"""
                INSERT INTO {self.schema_name}.document_toc (document_id, toc_json)
                VALUES (:doc_id, :toc_json)
                ON CONFLICT (document_id) DO UPDATE SET toc_json = EXCLUDED.toc_json
            """), {
                "doc_id": document_id,
                "toc_json": json.dumps(toc_items)
            })
            conn.commit()

    def get_toc(self, document_id: str) -> list[dict[str, Any]]:
        self._ensure_rich_tables()
        from sqlalchemy import text  # type: ignore
        with self._engine.connect() as conn:
            result = conn.execute(text(f"SELECT toc_json FROM {self.schema_name}.document_toc WHERE document_id = :doc_id"), {"doc_id": document_id})
            row = result.fetchone()
            if row and row[0]:
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return []

    def add_images(self, document_id: str, images: list[dict[str, Any]]) -> None:
        self._ensure_rich_tables()
        from sqlalchemy import text  # type: ignore
        with self._engine.connect() as conn:
            conn.execute(text(f"DELETE FROM {self.schema_name}.document_images WHERE document_id = :doc_id"), {"doc_id": document_id})
            for img in images:
                conn.execute(text(f"""
                    INSERT INTO {self.schema_name}.document_images 
                    (document_id, image_type, page_number, image_base64, caption, alt_text, bbox, width, height, metadata)
                    VALUES (:doc_id, :image_type, :page_number, :image_base64, :caption, :alt_text, :bbox, :width, :height, :metadata)
                """), {
                    "doc_id": document_id,
                    "image_type": img.get("image_type"),
                    "page_number": img.get("page_number"),
                    "image_base64": img.get("image_base64"),
                    "caption": img.get("caption"),
                    "alt_text": img.get("alt_text"),
                    "bbox": json.dumps(img.get("bbox")) if img.get("bbox") else None,
                    "width": img.get("width"),
                    "height": img.get("height"),
                    "metadata": json.dumps(img.get("metadata", {}))
                })
            conn.commit()

    def get_images(self, document_id: str) -> list[dict[str, Any]]:
        self._ensure_rich_tables()
        from sqlalchemy import text  # type: ignore
        with self._engine.connect() as conn:
            result = conn.execute(text(f"SELECT image_type, page_number, image_base64, caption, alt_text, bbox, width, height, metadata FROM {self.schema_name}.document_images WHERE document_id = :doc_id"), {"doc_id": document_id})
            rows = []
            for row in result:
                d = dict(row._mapping)
                if d.get("bbox") and isinstance(d["bbox"], str): d["bbox"] = json.loads(d["bbox"])
                if d.get("metadata") and isinstance(d["metadata"], str): d["metadata"] = json.loads(d["metadata"])
                rows.append(d)
            return rows

    def add_page_images(self, document_id: str, page_images: list[dict[str, Any]]) -> None:
        self._ensure_rich_tables()
        from sqlalchemy import text  # type: ignore
        with self._engine.connect() as conn:
            conn.execute(text(f"DELETE FROM {self.schema_name}.page_images WHERE document_id = :doc_id"), {"doc_id": document_id})
            for pg in page_images:
                conn.execute(text(f"""
                    INSERT INTO {self.schema_name}.page_images (document_id, page_number, image_base64, width, height)
                    VALUES (:doc_id, :page_number, :image_base64, :width, :height)
                """), {
                    "doc_id": document_id,
                    "page_number": pg.get("page_number"),
                    "image_base64": pg.get("image_base64"),
                    "width": pg.get("width"),
                    "height": pg.get("height")
                })
            conn.commit()

    def get_page_images(self, document_id: str, page_number: int) -> dict[str, Any]:
        self._ensure_rich_tables()
        from sqlalchemy import text  # type: ignore
        with self._engine.connect() as conn:
            result = conn.execute(text(f"SELECT image_base64, width, height FROM {self.schema_name}.page_images WHERE document_id = :doc_id AND page_number = :page_no"), {"doc_id": document_id, "page_no": page_number})
            row = result.fetchone()
            if row:
                d = dict(row._mapping)
                d["page_number"] = page_number
                return d
            return {}

    def get_page_images_for_pages(self, document_id: str, page_numbers: list[int]) -> list[dict[str, Any]]:
        self._ensure_rich_tables()
        from sqlalchemy import text  # type: ignore
        with self._engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT page_number, image_base64, width, height 
                FROM {self.schema_name}.page_images 
                WHERE document_id = :doc_id AND page_number = ANY(:page_nos)
            """), {"doc_id": document_id, "page_nos": page_numbers})
            return [dict(row._mapping) for row in result]

    def get_chunks_by_section(self, document_id: str, section_name: str) -> list[dict[str, Any]]:
        """Query chunks for a specific section using the headings metadata."""
        from sqlalchemy import text  # type: ignore
        chunks_table = f"data_{self.table_name}"
        with self._engine.connect() as conn:
            result = conn.execute(text(f"""
                SELECT id, text AS content, metadata_ AS metadata
                FROM {self.schema_name}.{chunks_table}
                WHERE metadata_->>'document_id' = :doc_id
                  AND EXISTS (
                      SELECT 1
                      FROM json_array_elements_text(COALESCE(metadata_->'headings', '[]'::json)) AS heading(value)
                      WHERE lower(btrim(heading.value)) = lower(btrim(:section_name))
                  )
            """), {
                "section_name": section_name,
                "doc_id": document_id
            })
            return [dict(row._mapping) for row in result]
