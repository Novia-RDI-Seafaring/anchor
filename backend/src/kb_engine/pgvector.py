"""Postgres/pgvector storage backend for ANCHOR KB.
Localized from KETJU to allow project-specific extensions without modifying external library.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List
import json

from ketju.rag.llama_index.contracts import LlamaIndexStorageBackend
from ketju.rag.llama_index.storage.pgvector import PgVectorStorageBackend

from llama_index.core import Settings

#not in use at the mmomen
class StorageBackend(PgVectorStorageBackend):
    """Storage strategy using Postgres + pgvector + postgres doc/index stores."""

    def __init__(
        self,
        **kwargs: Dict[str, Any]) -> None:
        super().__init__(**kwargs)
        from sqlalchemy import create_engine, make_url
        print("0....")
        print(self.database_url)
        # Persistent engine for sync operations (TOC, Images, etc.)
        self._engine = create_engine(self.database_url, pool_size=5, max_overflow=10)
        self._url = make_url(self.database_url)
        print("1....")
        self._ensure_rich_tables()
        print("2....")

    def _db_url(self):
        from sqlalchemy import make_url  # type: ignore

        return make_url(self.database_url or "")


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
        from sqlalchemy import text  # type: ignore
        with self._engine.connect() as conn:
            result = conn.execute(text(f"SELECT toc_json FROM {self.schema_name}.document_toc WHERE document_id = :doc_id"), {"doc_id": document_id})
            row = result.fetchone()
            if row and row[0]:
                return json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return []

    def add_images(self, document_id: str, images: list[dict[str, Any]]) -> None:
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
