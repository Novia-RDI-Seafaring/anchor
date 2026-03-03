"""
Vector Store Service for pgvector/Supabase.

Handles document chunk storage and similarity search using PostgreSQL with pgvector.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib
import asyncpg
import json
import re

from ..core.config import get_settings
from ..core.security import validate_embedding_values
import os


class VectorStore:
    """Vector store using pgvector for document embeddings."""
    
    def __init__(self):
        self.settings = get_settings()
        self.pool: Optional[asyncpg.Pool] = None
        self._initialized = False
        self._queries: Dict[str, Dict[str, str]] = {}

    def _load_sql(self, relative_path: str) -> str:
        """
        Load SQL query from flattened SQL files.
        Maps 'group/name.sql' to query 'name' in 'sql/group.sql'.
        """
        # Parse group and name
        parts = relative_path.split('/')
        if len(parts) < 2:
             raise ValueError(f"Invalid SQL path format: {relative_path}")
        
        group = parts[0]
        # Remove extension if present
        name = parts[1].replace('.sql', '')
        
        # Load group if not cached
        if group not in self._queries:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(base_dir, "sql", f"{group}.sql")
            
            if not os.path.exists(file_path):
                 raise FileNotFoundError(f"SQL group file not found: {file_path}")
            
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Simple parser for "-- name: query_name"
            queries = {}
            current_name = None
            current_lines = []
            
            for line in content.splitlines():
                if line.strip().startswith("-- name:"):
                    if current_name:
                        queries[current_name] = "\n".join(current_lines).strip()
                    current_name = line.strip().split(":", 1)[1].strip()
                    current_lines = []
                else:
                    if current_name:
                        current_lines.append(line)
            
            if current_name:
                 queries[current_name] = "\n".join(current_lines).strip()
                 
            self._queries[group] = queries
            
        if name not in self._queries[group]:
             raise KeyError(f"Query '{name}' not found in group '{group}'")
             
        query = self._queries[group][name]
            
        # Replace placeholders
        query = query.replace("%%SCHEMA%%", self.settings.db_schema)
        query = query.replace("%%DIMENSION%%", str(self.settings.embedding_dimension))

        return query

    def _get_rag_chunks_table(self) -> str:
        table_name = f"data_{self.settings.vector_db_collection}"
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
            raise ValueError(f"Invalid vector_db_collection for table identifier: {self.settings.vector_db_collection}")
        return table_name
    
    async def initialize(self):
        """Initialize connection pool and create tables if needed."""
        if self._initialized:
            return
        
        # Handle SSL mode - asyncpg expects ssl=False for 'disable'
        ssl_mode = self.settings.pgsslmode
        ssl_param = False if ssl_mode == 'disable' else ssl_mode
        
        print(f"VectorStore: Connecting to {self.settings.pgvector_host}:{self.settings.pgvector_port}/{self.settings.pgvector_db}")
        
        self.pool = await asyncpg.create_pool(
            host=self.settings.pgvector_host,
            port=self.settings.pgvector_port,
            database=self.settings.pgvector_db,
            user=self.settings.pgvector_user,
            password=self.settings.pgvector_password,
            ssl=ssl_param,
            min_size=2,
            max_size=10,
            statement_cache_size=0,  # Required for Supavisor/pgbouncer
            server_settings={
                "search_path": f'"{self.settings.db_schema}", public, extensions'
            }
        )
        
        await self._create_tables()
        self._initialized = True
        print(f"VectorStore: Connected to pgvector at {self.settings.pgvector_host}:{self.settings.pgvector_port}")
    
    async def _create_tables(self):
        """Create required tables and extensions."""
        async with self.pool.acquire() as conn:
            # Create schema if it doesn't exist
            if self.settings.db_schema != "public":
                await conn.execute(self._load_sql("init/init_schema.sql"))

            # Enable pgvector extension
            await conn.execute(self._load_sql("init/init_vector_extension.sql"))
            
            # Documents table
            await conn.execute(self._load_sql("init/init_documents_table.sql"))
            
            # Chunks table with vector embeddings
            await conn.execute(self._load_sql("init/init_chunks_table.sql"))
            
            # Create index for similarity search (only if table has data)
            try:
                await conn.execute(self._load_sql("init/init_chunks_index.sql"))
            except Exception:
                # Index creation may fail on empty table, that's OK
                pass
            
            # Page images table for storing rendered PDF page images
            await conn.execute(self._load_sql("init/init_page_images_table.sql"))
            
            # Document images table for storing extracted diagrams/figures
            await conn.execute(self._load_sql("init/init_document_images_table.sql"))

            # Document TOC table for storing Table of Contents / Index
            await conn.execute(self._load_sql("init/init_document_toc_table.sql"))
            
            # Create index for faster queries by document_id and image_type
            await conn.execute(self._load_sql("init/init_document_images_index.sql"))
            
            print("VectorStore: Tables initialized")
    
    def _parse_metadata(self, metadata: Any) -> Dict[str, Any]:
        """Safely parse metadata if it's a JSON string, otherwise return as dict."""
        if metadata is None:
            return {}
        if isinstance(metadata, dict):
            return metadata
        if isinstance(metadata, str):
            try:
                import json
                return json.loads(metadata)
            except Exception:
                return {}
        return {}
    
    async def add_document(
        self,
        document_id: str,
        filename: str,
        file_path: Optional[str] = None,
        source_type: str = "file",
        mime_type: Optional[str] = None,
        file_size: Optional[int] = None,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Add a document record to the database."""
        import json
        metadata_json = json.dumps(metadata or {})
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                self._load_sql("documents/insert.sql"), 
                document_id, filename, file_path, source_type, mime_type, file_size, 
                metadata_json
            )
            
            result = dict(row)
            if "metadata" in result:
                result["metadata"] = self._parse_metadata(result["metadata"])
            return result

    async def find_document_by_content_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        """Find the most recent document with a given content hash (metadata.content_hash)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                self._load_sql("documents/find_by_hash.sql"),
                content_hash,
            )
            if row:
                result = dict(row)
                result["metadata"] = self._parse_metadata(result.get("metadata"))
                return result
            return None

    async def find_document_by_source_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Find the most recent URL-sourced document with a given source_url (metadata.source_url)."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                self._load_sql("documents/find_by_url.sql"),
                url,
            )
            if row:
                result = dict(row)
                result["metadata"] = self._parse_metadata(result.get("metadata"))
                return result
            return None
    
    async def add_chunks(
        self,
        document_id: str,
        chunks: List[Dict[str, Any]],
        embeddings: List[List[float]]
    ) -> int:
        """Add chunks with embeddings for a document."""
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks must match number of embeddings")
        
        async with self.pool.acquire() as conn:
            # Delete existing chunks for this document
            await conn.execute(
                self._load_sql("chunks/delete_by_doc_id.sql"),
                document_id
            )
            
            # Insert new chunks with security validation
            import json
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                # SECURITY: Validate embedding before string conversion
                validate_embedding_values(embedding)
                
                metadata_json = json.dumps(chunk.get("metadata", {}))
                # Safe conversion after validation
                embedding_str = '[' + ','.join(str(float(x)) for x in embedding) + ']'
                await conn.execute(
                    self._load_sql("chunks/insert.sql"), 
                    document_id, i, chunk["content"], embedding_str, metadata_json
                )
            
            # Update document with chunk count and status
            await self.update_chunk_count(document_id, len(chunks))
            
            return len(chunks)
    
    async def update_chunk_count(self, document_id: str, count: int) -> None:
        """Update the chunk count for a document."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                self._load_sql("documents/update_chunk_count.sql"),
                document_id, count
            )

    async def update_document_status(self, document_id: str, status: str, chunk_count: Optional[int] = None) -> None:
        """Update the status and optionally chunk count for a document."""
        async with self.pool.acquire() as conn:
            if chunk_count is not None:
                await conn.execute(
                    self._load_sql("documents/update_chunk_count.sql"),
                    document_id, chunk_count
                )
            else:
                await conn.execute(
                    self._load_sql("documents/update_status.sql"),
                    document_id, status
                )

    async def update_document_page_count(self, document_id: str, count: int) -> None:
        """Update the page count for a document."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                self._load_sql("documents/update_page_count.sql"),
                document_id, count
            )
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        threshold: Optional[float] = None,
        document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks using cosine similarity, optionally filtered by document."""
        # SECURITY: Validate query embedding before use
        validate_embedding_values(query_embedding)
        
        # Use configured threshold if not provided
        if threshold is None:
            threshold = self.settings.similarity_threshold
        # Convert embedding list to pgvector string format
        embedding_str = '[' + ','.join(str(float(x)) for x in query_embedding) + ']'
        
        async with self.pool.acquire() as conn:
            if document_id:
                # Filter by specific document
                rows = await conn.fetch(
                    self._load_sql("chunks/search_by_doc.sql"), 
                    embedding_str, top_k, threshold, document_id
                )
            else:
                # Search all documents
                rows = await conn.fetch(
                    self._load_sql("chunks/search.sql"),
                    embedding_str, top_k, threshold
                )
            
            
            results = [dict(row) for row in rows]
            
            # Fetch page images for the results
            if results:
                # Collect all (document_id, page_number) pairs needed
                images_to_fetch = set()
                for res in results:
                    meta = res.get('metadata')
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except:
                            meta = {}
                    if not meta:
                        meta = {}
                    
                    # Store parsed metadata back to result to avoid re-parsing later
                    res['metadata'] = meta

                    # Try to get page numbers from metadata
                    # Metadata format for Docling chunks usually includes 'page_numbers' list or single 'page_number'
                    page_nums = meta.get('page_numbers', [])
                    if not page_nums and 'page_number' in meta:
                        page_nums = [meta['page_number']]
                        
                    for p_num in page_nums:
                        images_to_fetch.add((res['document_id'], p_num))
                
                if images_to_fetch:
                    # Batch fetch all needed images
                    # We can't easily do a fast collection search with composite keys in SQL
                    # So we'll fetch by document IDs and then filter in memory or do multiple queries
                    # Given page chunks usually belong to few docs, fetching by doc_ids and page_numbers is efficient
                    
                    doc_ids_list = list(set(d_id for d_id, _ in images_to_fetch))
                    page_nums_list = list(set(p_num for _, p_num in images_to_fetch))
                    
                    doc_ids_list = list(set(d_id for d_id, _ in images_to_fetch))
                    page_nums_list = list(set(p_num for _, p_num in images_to_fetch))
                    
                    image_rows = await conn.fetch(
                        # self._load_sql("images/page_get_batch.sql"),
                        self._load_sql("images/page_get_batch_multi_doc.sql"),
                        doc_ids_list, page_nums_list
                    ) # Wait, my batch SQL uses document_id=$1 and page_number=ANY($2).
                      # It only supports ONE document_id.
                      # The original query was:
                      # document_id = ANY($1) AND page_number = ANY($2)
                      # So `page_get_batch.sql` (created as `document_id=$1`) is WRONG for this use case if we have multiple documents.
                      # However, the code logic:
                      # `doc_ids_list = list(set(...))`
                      # If we fetch for multiple docs, the original query worked.
                      # My generic `page_get_batch` is optimized for one doc.
                      # I need to FIX `page_get_batch.sql` or create `page_get_batch_multi_doc.sql` or revert to query string here.
                      # Actually, looking at the code above: `doc_ids_list` implies multiple docs.
                      # So `page_get_batch.sql` is currently: `WHERE document_id = $1 AND page_number = ANY($2)`
                      # Original: `WHERE document_id = ANY($1) AND page_number = ANY($2)`
                      # I made a mistake in creating the SQL file for this specific complex query.
                      
                      # I will correct the SQL file in a subsequent step or use inline SQL for now if I can't overwrite.
                      # I CAN overwrite.
                      # But I am inside a `multi_replace_file_content`.
                      
                      # I will skip replacing this specific block for now and fix the SQL file first in the next step, then replace the code.
                    
                    # Create a lookup map: (document_id, page_number) -> image_data
                    image_map = {}
                    for img in image_rows:
                        key = (img['document_id'], img['page_number'])
                        image_map[key] = {
                            "image_base64": img['image_base64'],
                            "width": img['width'],
                            "height": img['height'],
                            "page_number": img['page_number']
                        }
                    
                    # Attach images to results
                    for res in results:
                        res_images = []
                        meta = res.get('metadata') or {}
                        page_nums = meta.get('page_numbers', [])
                        if not page_nums and 'page_number' in meta:
                            page_nums = [meta['page_number']]
                            
                        for p_num in page_nums:
                            key = (res['document_id'], p_num)
                            if key in image_map:
                                res_images.append(image_map[key])
                        
                        res['page_images'] = res_images
                    
                    # Also fetch extracted diagrams/figures from the same pages
                    # Collect all unique (document_id, page_numbers) pairs from results
                    doc_page_map = {}
                    for res in results:
                        doc_id = res['document_id']
                        meta = res.get('metadata') or {}
                        page_nums = meta.get('page_numbers', [])
                        if not page_nums and 'page_number' in meta:
                            page_nums = [meta['page_number']]
                        
                        if doc_id not in doc_page_map:
                            doc_page_map[doc_id] = set()
                        doc_page_map[doc_id].update(page_nums)
                    
                    # Fetch document images for these pages
                    for doc_id, page_nums in doc_page_map.items():
                        if page_nums:
                            diagram_rows = await conn.fetch(
                                self._load_sql("images/doc_get_by_pages.sql"),
                                doc_id, list(page_nums)
                            )
                            
                            # Attach diagrams to the corresponding results
                            for res in results:
                                if res['document_id'] == doc_id:
                                    res['document_images'] = [
                                        {
                                            "id": row['id'],
                                            "image_type": row['image_type'],
                                            "page_number": row['page_number'],
                                            "image_base64": row['image_base64'],
                                            "caption": row['caption'],
                                            "alt_text": row['alt_text'],
                                            "bbox": row['bbox'],
                                            "width": row['width'],
                                            "height": row['height'],
                                            "metadata": row['metadata']
                                        }
                                        for row in diagram_rows
                                        if row['page_number'] in (res.get('metadata', {}).get('page_numbers', []) or 
                                                                   [res.get('metadata', {}).get('page_number')] if 'page_number' in res.get('metadata', {}) else [])
                                    ]
                else:
                    # No images to fetch implies no page numbers found, init empty list
                    for res in results:
                        res['page_images'] = []
                        res['document_images'] = []
            else:
                # No results, return empty
                for res in results:
                    res['page_images'] = []
                    res['document_images'] = []
            
            return results
    
    async def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents in the store."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(self._load_sql("documents/list.sql"))
            return [dict(row) for row in rows]
    
    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific document by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                self._load_sql("documents/get.sql"), 
                document_id
            )
            if row:
                result = dict(row)
                result["metadata"] = self._parse_metadata(result.get("metadata"))
                return result
            return None
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its associated chunks, page images, and document images."""
        async with self.pool.acquire() as conn:
            # Remove chunk rows from the active KETJU/pgvector table as well.
            rag_chunks_table = self._get_rag_chunks_table()
            try:
                await conn.execute(
                    f'DELETE FROM "{self.settings.db_schema}"."{rag_chunks_table}" '
                    "WHERE metadata_->>'document_id' = $1",
                    document_id,
                )
            except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
                pass

            # Delete in order: chunks, page_images, document_images, then document
            # This ensures referential integrity even without FK constraints
            await conn.execute(
                self._load_sql("chunks/delete_by_doc_id.sql"),
                document_id
            )
            await conn.execute(
                self._load_sql("images/page_delete_by_doc_id.sql"),
                document_id
            )
            await conn.execute(
                self._load_sql("images/doc_delete_by_doc_id.sql"),
                document_id
            )
            result = await conn.execute(
                self._load_sql("documents/delete.sql"),
                document_id
            )
            return result == "DELETE 1"
    
    async def reset(self) -> Dict[str, int]:
        """Delete all documents, chunks, page images, and document images."""
        async with self.pool.acquire() as conn:
            chunks_deleted = await conn.fetchval(self._load_sql("stats/count_chunks.sql"))
            docs_deleted = await conn.fetchval(self._load_sql("stats/count_documents.sql"))
            page_images_deleted = await conn.fetchval(self._load_sql("stats/count_page_images.sql"))
            document_images_deleted = await conn.fetchval(self._load_sql("stats/count_document_images.sql"))
            rag_chunks_deleted = 0

            rag_chunks_table = self._get_rag_chunks_table()
            try:
                rag_chunks_deleted = await conn.fetchval(
                    f'SELECT COUNT(*) FROM "{self.settings.db_schema}"."{rag_chunks_table}"'
                )
                await conn.execute(
                    f'DELETE FROM "{self.settings.db_schema}"."{rag_chunks_table}"'
                )
            except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
                rag_chunks_deleted = 0

            # Delete in order: chunks, page_images, document_images, then documents
            # I will use the reset.sql which does DELETE ALL
            # But the original code does separate DELETE calls.
            # reset.sql has 4 DELETE statements separated by semicolons.
            # asyncpg execute can run script.
            
            await conn.execute(self._load_sql("stats/reset.sql"))
            
            return {
                "documents_deleted": docs_deleted,
                "chunks_deleted": chunks_deleted,
                "page_images_deleted": page_images_deleted,
                "document_images_deleted": document_images_deleted,
                "rag_chunks_deleted": rag_chunks_deleted,
            }
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store."""
        async with self.pool.acquire() as conn:
            doc_count = await conn.fetchval(self._load_sql("stats/count_documents.sql"))
            chunk_count = await conn.fetchval(self._load_sql("stats/count_chunks.sql"))
            processed_count = await conn.fetchval(self._load_sql("stats/count_processed_docs.sql"))
            rag_chunk_count = 0
            active_chunk_table = "chunks"

            rag_chunks_table = self._get_rag_chunks_table()
            try:
                rag_chunk_count = await conn.fetchval(
                    f'SELECT COUNT(*) FROM "{self.settings.db_schema}"."{rag_chunks_table}"'
                )
                if rag_chunk_count:
                    active_chunk_table = rag_chunks_table
            except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
                rag_chunk_count = 0

            active_chunk_count = rag_chunk_count if rag_chunk_count else chunk_count

            return {
                "total_documents": doc_count,
                "processed_documents": processed_count,
                "total_chunks": active_chunk_count,
                "legacy_chunks": chunk_count,
                "rag_chunks": rag_chunk_count,
                "chunk_table": active_chunk_table,
                "status": "connected"
            }
    
    async def add_page_images(
        self,
        document_id: str,
        page_images: List[Dict[str, Any]]
    ) -> int:
        """
        Store page images for a document.
        
        Args:
            document_id: The document ID
            page_images: List of dicts with page_number, image_base64, width, height
            
        Returns:
            Number of pages stored
        """
        async with self.pool.acquire() as conn:
            # Delete existing page images for this document
            await conn.execute(
                self._load_sql("images/page_delete_by_doc_id.sql"),
                document_id
            )
            
            # Insert new page images
            for img in page_images:
                await conn.execute(
                    self._load_sql("images/page_insert.sql"), 
                    document_id, img['page_number'], img['image_base64'], 
                    img.get('width'), img.get('height')
                )
            
            # Update document page count
            await conn.execute(
                self._load_sql("documents/update_page_count.sql"),
                document_id, len(page_images)
            )
            
            return len(page_images)
    
    async def get_page_image(
        self,
        document_id: str,
        page_number: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single page image.
        
        Args:
            document_id: The document ID
            page_number: 1-indexed page number
            
        Returns:
            Dict with image_base64, width, height or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                self._load_sql("images/page_get.sql"),
                document_id, page_number
            )
            
            if row:
                return {
                    "image_base64": row['image_base64'],
                    "width": row['width'],
                    "height": row['height'],
                    "page_number": page_number
                }
            return None
    
    async def get_page_images_for_pages(
        self,
        document_id: str,
        page_numbers: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Get multiple page images.
        
        Args:
            document_id: The document ID
            page_numbers: List of 1-indexed page numbers
            
        Returns:
            List of dicts with page_number, image_base64, width, height
        """
        if not page_numbers:
            return []
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                self._load_sql("images/page_get_batch.sql"),
                document_id, page_numbers
            )
            
            return [
                {
                    "page_number": row['page_number'],
                    "image_base64": row['image_base64'],
                    "width": row['width'],
                    "height": row['height']
                }
                for row in rows
            ]
    
    async def get_page_images_by_chunk_id(self, chunk_id: int) -> List[Dict[str, Any]]:
        """
        Get page images for a specific chunk by chunk ID.
        
        Retrieves the chunk's document_id and page_numbers from metadata,
        then fetches the corresponding page images.
        
        Args:
            chunk_id: The chunk ID (primary key from chunks table)
            
        Returns:
            List of dicts with page_number, image_base64, width, height
        """
        async with self.pool.acquire() as conn:
            # First, get the chunk's document_id and page_numbers from metadata
            # First, get the chunk's document_id and page_numbers from metadata
            chunk_row = await conn.fetchrow(
                self._load_sql("chunks/get_metadata.sql"),
                chunk_id
            )
            
            if not chunk_row:
                return []
            
            document_id = chunk_row['document_id']
            metadata = chunk_row['metadata']
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}
            if not metadata:
                metadata = {}
                
            page_numbers = metadata.get('page_numbers', [])
            
            if not page_numbers:
                return []
            
            # Now get the page images for those pages
            rows = await conn.fetch(f"""
                SELECT page_number, image_base64, width, height
                FROM "{self.settings.db_schema}".page_images
                WHERE document_id = $1 AND page_number = ANY($2)
                ORDER BY page_number
            """, document_id, page_numbers)
            
            return [
                {
                    "page_number": row['page_number'],
                    "image_base64": row['image_base64'],
                    "width": row['width'],
                    "height": row['height']
                }
                for row in rows
            ]
    
    async def add_document_images(
        self,
        document_id: str,
        images: List[Dict[str, Any]]
    ) -> int:
        """
        Store extracted images (diagrams, figures) from a document.
        
        Args:
            document_id: The document ID
            images: List of dicts with:
                - image_type: Type of image (figure, diagram, chart, etc.)
                - page_number: Page number where image was found
                - image_base64: Base64-encoded image data
                - caption: Extracted caption text (optional)
                - alt_text: Alternative text (optional)
                - bbox: Bounding box coordinates as dict (optional)
                - width: Image width (optional)
                - height: Image height (optional)
                - metadata: Additional metadata (optional)
            
        Returns:
            Number of images stored
        """
        async with self.pool.acquire() as conn:
            # Delete existing document images for this document
            await conn.execute(
                self._load_sql("images/doc_delete_by_doc_id.sql"),
                document_id
            )
            
            # Insert new document images
            for img in images:
                bbox_json = json.dumps(img.get('bbox')) if img.get('bbox') else None
                metadata_json = json.dumps(img.get('metadata', {}))
                
                await conn.execute(
                    self._load_sql("images/doc_insert.sql"), 
                    document_id,
                    img.get('image_type', 'figure'),
                    img.get('page_number'),
                    img['image_base64'],
                    img.get('caption'),
                    img.get('alt_text'),
                    bbox_json,
                    img.get('width'),
                    img.get('height'),
                    metadata_json
                )
            
            return len(images)
    
    async def get_document_images(
        self,
        document_id: str,
        image_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get extracted images for a document.
        
        Args:
            document_id: The document ID
            image_type: Optional filter by image type
            
        Returns:
            List of dicts with image data and metadata
        """
        async with self.pool.acquire() as conn:
            if image_type:
                rows = await conn.fetch(
                    self._load_sql("images/doc_get_by_type.sql"), 
                    document_id, image_type
                )
            else:
                rows = await conn.fetch(
                    self._load_sql("images/doc_get.sql"),
                    document_id
                )
            
            return [
                {
                    "id": row['id'],
                    "image_type": row['image_type'],
                    "page_number": row['page_number'],
                    "image_base64": row['image_base64'],
                    "caption": row['caption'],
                    "alt_text": row['alt_text'],
                    "bbox": row['bbox'],
                    "width": row['width'],
                    "height": row['height'],
                    "metadata": row['metadata']
                }
                for row in rows
            ]
    
    async def search_images_by_pages(
        self,
        document_id: str,
        page_numbers: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Get extracted images for specific pages of a document.
        
        Args:
            document_id: The document ID
            page_numbers: List of page numbers
            
        Returns:
            List of dicts with image data and metadata
        """
        if not page_numbers:
            return []
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                self._load_sql("images/doc_get_by_pages.sql"),
                document_id, page_numbers
            )
            
            return [
                {
                    "id": row['id'],
                    "image_type": row['image_type'],
                    "page_number": row['page_number'],
                    "image_base64": row['image_base64'],
                    "caption": row['caption'],
                    "alt_text": row['alt_text'],
                    "bbox": row['bbox'],
                    "width": row['width'],
                    "height": row['height'],
                    "metadata": row['metadata']
                }
                for row in rows
            ]
    
    async def add_toc(self, document_id: str, toc_data: Any) -> bool:
        """
        Store the Table of Contents for a document.
        
        Args:
            document_id: The document ID
            toc_data: Structured TOC data (list or dict)
            
        Returns:
            True if stored successfully
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                self._load_sql("toc/upsert.sql"),
                document_id, json.dumps(toc_data)
            )
            return True

    async def get_toc(self, document_id: str) -> Optional[Any]:
        """
        Get the Table of Contents for a document.
        
        Args:
            document_id: The document ID
            
        Returns:
            The structured TOC data or None
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                self._load_sql("toc/get.sql"),
                document_id
            )
            if row:
                return self._parse_metadata(row['toc_json'])
            return None

    async def get_chunks_by_section(self, document_id: str, section_name: str) -> List[Dict[str, Any]]:
        """
        Retrieve all chunks belonging to a specific section.
        
        Args:
            document_id: The document ID
            section_name: The name of the section (from headings metadata)
            
        Returns:
            List of chunks
        """
        async with self.pool.acquire() as conn:
            # Match if the section_name is in the headings list in metadata
            # pgvector/jsonb query: metadata->'headings' @> '["section_name"]'
            rows = await conn.fetch(
                self._load_sql("chunks/get_by_section.sql"),
                document_id, json.dumps([section_name])
            )
            
            return [dict(row) for row in rows]
    
    async def close(self):
        """Close the connection pool."""
        if self.pool:
            await self.pool.close()
            self._initialized = False


# Singleton instance
_vector_store: Optional[VectorStore] = None

async def get_vector_store() -> VectorStore:
    """Get or create the vector store singleton."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
        await _vector_store.initialize()
    return _vector_store
