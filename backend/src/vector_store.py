"""
Vector Store Service for pgvector/Supabase.

Handles document chunk storage and similarity search using PostgreSQL with pgvector.
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib
import asyncpg

from .config import get_settings


class VectorStore:
    """Vector store using pgvector for document embeddings."""
    
    def __init__(self):
        self.settings = get_settings()
        self.pool: Optional[asyncpg.Pool] = None
        self._initialized = False
    
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
            statement_cache_size=0  # Required for Supavisor/pgbouncer
        )
        
        await self._create_tables()
        self._initialized = True
        print(f"VectorStore: Connected to pgvector at {self.settings.pgvector_host}:{self.settings.pgvector_port}")
    
    async def _create_tables(self):
        """Create required tables and extensions."""
        async with self.pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Documents table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id SERIAL PRIMARY KEY,
                    document_id TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    file_path TEXT,
                    source_type TEXT DEFAULT 'file',
                    mime_type TEXT,
                    file_size INTEGER,
                    page_count INTEGER,
                    chunk_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata JSONB DEFAULT '{}'
                );
            """)
            
            # Chunks table with vector embeddings (no FK constraint for simplicity)
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS chunks (
                    id SERIAL PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector({self.settings.embedding_dimension}),
                    metadata JSONB DEFAULT '{{}}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(document_id, chunk_index)
                );
            """)
            
            # Create index for similarity search (only if table has data)
            try:
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS chunks_embedding_idx 
                    ON chunks USING hnsw (embedding vector_cosine_ops);
                """)
            except Exception:
                # Index creation may fail on empty table, that's OK
                pass
            
            # Page images table for storing rendered PDF page images
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS page_images (
                    id SERIAL PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    image_base64 TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(document_id, page_number)
                );
            """)
            
            print("VectorStore: Tables initialized")
    
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
            row = await conn.fetchrow("""
                INSERT INTO documents (document_id, filename, file_path, source_type, mime_type, file_size, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                ON CONFLICT (document_id) DO UPDATE SET
                    filename = EXCLUDED.filename,
                    file_path = EXCLUDED.file_path,
                    source_type = EXCLUDED.source_type,
                    mime_type = EXCLUDED.mime_type,
                    file_size = EXCLUDED.file_size,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, document_id, filename, status, created_at
            """, document_id, filename, file_path, source_type, mime_type, file_size, 
                metadata_json)
            
            return dict(row)
    
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
                "DELETE FROM chunks WHERE document_id = $1",
                document_id
            )
            
            # Insert new chunks
            import json
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                metadata_json = json.dumps(chunk.get("metadata", {}))
                # Convert embedding list to pgvector string format: [1,2,3]
                embedding_str = '[' + ','.join(str(x) for x in embedding) + ']'
                await conn.execute("""
                    INSERT INTO chunks (document_id, chunk_index, content, embedding, metadata)
                    VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                """, document_id, i, chunk["content"], embedding_str, metadata_json)
            
            # Update document with chunk count and status
            await conn.execute("""
                UPDATE documents 
                SET chunk_count = $2, status = 'processed', updated_at = CURRENT_TIMESTAMP
                WHERE document_id = $1
            """, document_id, len(chunks))
            
            return len(chunks)
    
    async def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        threshold: Optional[float] = None,
        document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar chunks using cosine similarity, optionally filtered by document."""
        # Use configured threshold if not provided
        if threshold is None:
            threshold = self.settings.similarity_threshold
        # Convert embedding list to pgvector string format
        embedding_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
        
        async with self.pool.acquire() as conn:
            if document_id:
                # Filter by specific document
                rows = await conn.fetch("""
                    SELECT 
                        c.id,
                        c.content,
                        c.metadata,
                        c.document_id,
                        d.filename,
                        1 - (c.embedding <=> $1::vector) as similarity
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.document_id
                    WHERE c.document_id = $4
                      AND 1 - (c.embedding <=> $1::vector) > $3
                    ORDER BY c.embedding <=> $1::vector
                    LIMIT $2
                """, embedding_str, top_k, threshold, document_id)
            else:
                # Search all documents
                rows = await conn.fetch("""
                    SELECT 
                        c.id,
                        c.content,
                        c.metadata,
                        c.document_id,
                        d.filename,
                        1 - (c.embedding <=> $1::vector) as similarity
                    FROM chunks c
                    JOIN documents d ON c.document_id = d.document_id
                    WHERE 1 - (c.embedding <=> $1::vector) > $3
                    ORDER BY c.embedding <=> $1::vector
                    LIMIT $2
                """, embedding_str, top_k, threshold)
            
            return [dict(row) for row in rows]
    
    async def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents in the store."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, document_id, filename, source_type, mime_type, 
                       file_size, chunk_count, status, created_at, updated_at
                FROM documents
                ORDER BY created_at DESC
            """)
            return [dict(row) for row in rows]
    
    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific document by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM documents WHERE document_id = $1
            """, document_id)
            return dict(row) if row else None
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its chunks."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM documents WHERE document_id = $1",
                document_id
            )
            return result == "DELETE 1"
    
    async def reset(self) -> Dict[str, int]:
        """Delete all documents and chunks."""
        async with self.pool.acquire() as conn:
            chunks_deleted = await conn.fetchval("SELECT COUNT(*) FROM chunks")
            docs_deleted = await conn.fetchval("SELECT COUNT(*) FROM documents")
            
            await conn.execute("DELETE FROM chunks")
            await conn.execute("DELETE FROM documents")
            
            return {"documents_deleted": docs_deleted, "chunks_deleted": chunks_deleted}
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store."""
        async with self.pool.acquire() as conn:
            doc_count = await conn.fetchval("SELECT COUNT(*) FROM documents")
            chunk_count = await conn.fetchval("SELECT COUNT(*) FROM chunks")
            processed_count = await conn.fetchval(
                "SELECT COUNT(*) FROM documents WHERE status = 'processed'"
            )
            
            return {
                "total_documents": doc_count,
                "processed_documents": processed_count,
                "total_chunks": chunk_count,
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
                "DELETE FROM page_images WHERE document_id = $1",
                document_id
            )
            
            # Insert new page images
            for img in page_images:
                await conn.execute("""
                    INSERT INTO page_images (document_id, page_number, image_base64, width, height)
                    VALUES ($1, $2, $3, $4, $5)
                """, document_id, img['page_number'], img['image_base64'], 
                    img.get('width'), img.get('height'))
            
            # Update document page count
            await conn.execute("""
                UPDATE documents 
                SET page_count = $2, updated_at = CURRENT_TIMESTAMP
                WHERE document_id = $1
            """, document_id, len(page_images))
            
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
            row = await conn.fetchrow("""
                SELECT image_base64, width, height
                FROM page_images
                WHERE document_id = $1 AND page_number = $2
            """, document_id, page_number)
            
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
            rows = await conn.fetch("""
                SELECT page_number, image_base64, width, height
                FROM page_images
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
            chunk_row = await conn.fetchrow("""
                SELECT document_id, metadata
                FROM chunks
                WHERE id = $1
            """, chunk_id)
            
            if not chunk_row:
                return []
            
            document_id = chunk_row['document_id']
            metadata = chunk_row['metadata'] or {}
            page_numbers = metadata.get('page_numbers', [])
            
            if not page_numbers:
                return []
            
            # Now get the page images for those pages
            rows = await conn.fetch("""
                SELECT page_number, image_base64, width, height
                FROM page_images
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

