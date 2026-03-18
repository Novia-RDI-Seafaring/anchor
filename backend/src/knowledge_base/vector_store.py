"""Document registry plus KETJU storage helpers."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import asyncio

import asyncpg

from ..core.config import get_settings


_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class VectorStore:
    """Registry for uploaded documents plus cleanup helpers for live KETJU tables."""

    def __init__(self):
        self.settings = get_settings()
        self.pool: Optional[asyncpg.Pool] = None
        self._initialized = False
        self._queries: Dict[str, Dict[str, str]] = {}

    def _load_sql(self, relative_path: str) -> str:
        """Load a named query from the flattened SQL files."""
        parts = relative_path.split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid SQL path format: {relative_path}")

        group = parts[0]
        name = parts[1].replace(".sql", "")

        if group not in self._queries:
            file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sql", f"{group}.sql")
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"SQL group file not found: {file_path}")

            queries: Dict[str, str] = {}
            current_name: str | None = None
            current_lines: List[str] = []

            with open(file_path, "r", encoding="utf-8") as handle:
                for line in handle.read().splitlines():
                    if line.strip().startswith("-- name:"):
                        if current_name:
                            queries[current_name] = "\n".join(current_lines).strip()
                        current_name = line.strip().split(":", 1)[1].strip()
                        current_lines = []
                    elif current_name:
                        current_lines.append(line)

            if current_name:
                queries[current_name] = "\n".join(current_lines).strip()

            self._queries[group] = queries

        if name not in self._queries[group]:
            raise KeyError(f"Query '{name}' not found in group '{group}'")

        query = self._queries[group][name]
        query = query.replace("%%SCHEMA%%", self.settings.db_schema)
        query = query.replace("%%DIMENSION%%", str(self.settings.embedding_dimension))
        return query

    def _validated_identifier(self, identifier: str, *, label: str) -> str:
        if not _IDENTIFIER_RE.fullmatch(identifier):
            raise ValueError(f"Invalid {label}: {identifier}")
        return identifier

    def _rag_schema_name(self) -> str:
        return self._validated_identifier(self.settings.ketju_schema_name, label="ketju schema")

    def _rag_vector_table_name(self) -> str:
        return self._validated_identifier(f"data_{self.settings.ketju_table_name}", label="ketju vector table")

    def _rag_indexstore_table_name(self) -> str:
        return self._validated_identifier(
            f"data_{self.settings.ketju_table_name}_indexstore",
            label="ketju indexstore table",
        )

    def _rag_docstore_table_name(self) -> str:
        return self._validated_identifier(
            f"data_{self.settings.ketju_table_name}_docstore",
            label="ketju docstore table",
        )

    async def initialize(self) -> None:
        """Initialize the asyncpg pool and the app-owned registry table."""
        if self._initialized:
            return

        ssl_mode = self.settings.pgsslmode
        ssl_param = False if ssl_mode == "disable" else ssl_mode

        print(
            f"VectorStore: Connecting to {self.settings.pgvector_host}:"
            f"{self.settings.pgvector_port}/{self.settings.pgvector_db}"
        )

        self.pool = await asyncpg.create_pool(
            host=self.settings.pgvector_host,
            port=self.settings.pgvector_port,
            database=self.settings.pgvector_db,
            user=self.settings.pgvector_user,
            password=self.settings.pgvector_password,
            ssl=ssl_param,
            min_size=2,
            max_size=10,
            statement_cache_size=0,
            server_settings={"search_path": f'"{self.settings.db_schema}", public, extensions'},
        )

        await self._create_tables()
        self._initialized = True
        print(f"VectorStore: Connected to pgvector at {self.settings.pgvector_host}:{self.settings.pgvector_port}")

    async def _create_tables(self) -> None:
        async with self.pool.acquire() as conn:
            if self.settings.db_schema != "public":
                await conn.execute(self._load_sql("init/init_schema.sql"))
            await conn.execute(self._load_sql("init/init_vector_extension.sql"))
            await conn.execute(self._load_sql("init/init_documents_table.sql"))
            print("VectorStore: Document registry initialized")

    def _parse_metadata(self, metadata: Any) -> Dict[str, Any]:
        if metadata is None:
            return {}
        if isinstance(metadata, dict):
            return metadata
        if isinstance(metadata, str):
            try:
                return json.loads(metadata)
            except Exception:
                return {}
        return {}

    async def _table_exists(self, conn: asyncpg.Connection, schema_name: str, table_name: str) -> bool:
        return bool(
            await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = $1 AND table_name = $2
                )
                """,
                schema_name,
                table_name,
            )
        )

    async def _count_rows(self, conn: asyncpg.Connection, schema_name: str, table_name: str) -> int:
        if not await self._table_exists(conn, schema_name, table_name):
            return 0
        return int(await conn.fetchval(f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"'))

    async def add_document(
        self,
        document_id: str,
        filename: str,
        file_path: Optional[str] = None,
        source_type: str = "file",
        mime_type: Optional[str] = None,
        file_size: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        metadata_json = json.dumps(metadata or {})

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                self._load_sql("documents/insert.sql"),
                document_id,
                filename,
                file_path,
                source_type,
                mime_type,
                file_size,
                metadata_json,
            )
            result = dict(row)
            if "metadata" in result:
                result["metadata"] = self._parse_metadata(result["metadata"])
            return result

    async def find_document_by_content_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(self._load_sql("documents/find_by_hash.sql"), content_hash)
            if not row:
                return None
            result = dict(row)
            result["metadata"] = self._parse_metadata(result.get("metadata"))
            return result

    async def find_document_by_source_url(self, url: str) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(self._load_sql("documents/find_by_url.sql"), url)
            if not row:
                return None
            result = dict(row)
            result["metadata"] = self._parse_metadata(result.get("metadata"))
            return result

    async def update_chunk_count(self, document_id: str, count: int) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(self._load_sql("documents/update_chunk_count.sql"), document_id, count)

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        chunk_count: Optional[int] = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            if chunk_count is not None:
                await conn.execute(self._load_sql("documents/update_chunk_count.sql"), document_id, chunk_count)
            else:
                await conn.execute(self._load_sql("documents/update_status.sql"), document_id, status)

    async def list_documents(self) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(self._load_sql("documents/list.sql"))
            return [dict(row) for row in rows]

    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(self._load_sql("documents/get.sql"), document_id)
            if not row:
                return None
            result = dict(row)
            result["metadata"] = self._parse_metadata(result.get("metadata"))
            return result

    async def _delete_rag_rows_with_conn(
        self,
        conn: asyncpg.Connection,
        *,
        document_id: str,
        file_path: str | None = None,
        filename: str | None = None,
    ) -> None:
        schema_name = self._rag_schema_name()
        table_name = self._rag_vector_table_name()

        predicates = ["metadata_->>'document_id' = $1"]
        params: List[str] = [document_id]

        if file_path:
            predicates.append(f"metadata_->>'filepath' = ${len(params) + 1}")
            params.append(file_path)

        if filename:
            placeholder = f"${len(params) + 1}"
            predicates.append(f"metadata_->>'filename' = {placeholder}")
            predicates.append(f"metadata_->'origin'->>'filename' = {placeholder}")
            params.append(filename)

        try:
            await conn.execute(
                f'DELETE FROM "{schema_name}"."{table_name}" WHERE ' + " OR ".join(predicates),
                *params,
            )
        except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
            pass

    async def delete_rag_chunks(
        self,
        document_id: str,
        file_path: str | None = None,
        filename: str | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await self._delete_rag_rows_with_conn(
                conn,
                document_id=document_id,
                file_path=file_path,
                filename=filename,
            )

    async def delete_document(self, document_id: str) -> bool:
        document = await self.get_document(document_id)
        file_path = document.get("file_path") if document else None
        filename = document.get("filename") if document else None

        async with self.pool.acquire() as conn:
            await self._delete_rag_rows_with_conn(
                conn,
                document_id=document_id,
                file_path=file_path,
                filename=filename,
            )
            result = await conn.execute(self._load_sql("documents/delete.sql"), document_id)
            return result == "DELETE 1"

    async def reset(self) -> Dict[str, int]:
        async with self.pool.acquire() as conn:
            docs_deleted = int(await conn.fetchval(self._load_sql("stats/count_documents.sql")))
            processed_docs = int(await conn.fetchval(self._load_sql("stats/count_processed_docs.sql")))

            rag_schema = self._rag_schema_name()
            rag_vector_table = self._rag_vector_table_name()
            rag_indexstore_table = self._rag_indexstore_table_name()
            rag_docstore_table = self._rag_docstore_table_name()

            rag_vectors_deleted = await self._count_rows(conn, rag_schema, rag_vector_table)
            rag_indexstore_deleted = await self._count_rows(conn, rag_schema, rag_indexstore_table)
            rag_docstore_deleted = await self._count_rows(conn, rag_schema, rag_docstore_table)

            for table_name in (rag_vector_table, rag_indexstore_table, rag_docstore_table):
                if await self._table_exists(conn, rag_schema, table_name):
                    await conn.execute(f'DELETE FROM "{rag_schema}"."{table_name}"')

            await conn.execute(self._load_sql("stats/reset_documents.sql"))

            return {
                "documents_deleted": docs_deleted,
                "processed_documents_deleted": processed_docs,
                "rag_vectors_deleted": rag_vectors_deleted,
                "rag_indexstore_deleted": rag_indexstore_deleted,
                "rag_docstore_deleted": rag_docstore_deleted,
            }

    async def get_stats(self) -> Dict[str, Any]:
        async with self.pool.acquire() as conn:
            doc_count = int(await conn.fetchval(self._load_sql("stats/count_documents.sql")))
            processed_count = int(await conn.fetchval(self._load_sql("stats/count_processed_docs.sql")))

            rag_schema = self._rag_schema_name()
            rag_vector_table = self._rag_vector_table_name()
            rag_indexstore_table = self._rag_indexstore_table_name()
            rag_docstore_table = self._rag_docstore_table_name()

            rag_vector_rows = await self._count_rows(conn, rag_schema, rag_vector_table)
            rag_indexstore_rows = await self._count_rows(conn, rag_schema, rag_indexstore_table)
            rag_docstore_rows = await self._count_rows(conn, rag_schema, rag_docstore_table)

            return {
                "total_documents": doc_count,
                "processed_documents": processed_count,
                "rag_vector_rows": rag_vector_rows,
                "rag_indexstore_rows": rag_indexstore_rows,
                "rag_docstore_rows": rag_docstore_rows,
                "rag_schema": rag_schema,
                "rag_vector_table": rag_vector_table,
                "rag_indexstore_table": rag_indexstore_table,
                "rag_docstore_table": rag_docstore_table,
                "status": "connected",
            }

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self._initialized = False


_vector_store: Optional[VectorStore] = None
_vector_store_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _vector_store_lock
    if _vector_store_lock is None:
        _vector_store_lock = asyncio.Lock()
    return _vector_store_lock


async def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is not None:
        return _vector_store
    async with _get_lock():
        if _vector_store is None:
            vs = VectorStore()
            await vs.initialize()
            _vector_store = vs
    return _vector_store
