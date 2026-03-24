"""
Document Service.

Orchestrates document lifecycle: upload → ingest (via RagEngine) → search → delete.
"""

import os
import hashlib
import aiofiles
from typing import Optional, Dict, Any, List
from pathlib import Path

from ..core.config import get_settings
from ..core.provenance import build_retrieved_chunk, create_retrieval_id, get_current_trace_id
from ..api.file_service import get_file_service
from ..kb_engine.rag_engine import get_rag_engine
from .vector_store import get_vector_store


class DocumentService:
    """Service for document ingestion and management."""
    
    def __init__(self):
        self.settings = get_settings()
        self.uploads_dir = self.settings.uploads_path
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
    
    def _generate_document_id(self, filename: str, content_hash: Optional[str] = None) -> str:
        """
        Generate a unique document ID using SHA256.
        Format: <timestamp_ms>-<hash_prefix>
        """
        from datetime import datetime
        
        timestamp_ms = int(datetime.utcnow().timestamp() * 1000)
        base = f"{filename}-{content_hash or ''}-{timestamp_ms}"
        hash_digest = hashlib.sha256(base.encode()).hexdigest()[:16]
        
        return f"{timestamp_ms}-{hash_digest}"
    
    async def upload_file(
        self,
        filename: str,
        content: bytes,
        process_immediately: bool = True,
        preserve_images: bool = True,
        preserve_tables: bool = True,
        enable_ocr: bool = False,
        table_mode: str = "fast"
    ) -> Dict[str, Any]:
        """
        Upload and optionally process a file.
        
        Args:
            filename: Original filename
            content: File content as bytes
            process_immediately: Whether to process right away
            preserve_images: Enable image extraction
            preserve_tables: Enable table extraction
            enable_ocr: Enable OCR for scanned documents
            table_mode: Table extraction mode ('fast' or 'accurate')
            
        Returns:
            Document info dict
        """
        skip_duplicates = os.getenv("SKIP_DUPLICATE_INGEST", "0").strip().lower() in {"1", "true", "yes", "y"}

        content_hash = hashlib.md5(content).hexdigest()

        vector_store = await get_vector_store()
        if skip_duplicates:
            existing = await vector_store.find_document_by_content_hash(content_hash)
            if existing:
                if process_immediately and existing.get("status") != "processed":
                    await self.process_document(existing["document_id"])
                    refreshed = await vector_store.get_document(existing["document_id"])
                    return refreshed or existing
                return existing

        # Save file to uploads directory
        file_path = self.uploads_dir / filename
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        document_id = self._generate_document_id(filename, content_hash)
        
        ext = Path(filename).suffix.lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.html': 'text/html',
        }
        mime_type = mime_types.get(ext, 'application/octet-stream')
        
        doc_info = await vector_store.add_document(
            document_id=document_id,
            filename=filename,
            file_path=str(file_path),
            source_type="file",
            mime_type=mime_type,
            file_size=len(content),
            metadata={
                "content_hash": content_hash,
                "preserve_images": preserve_images,
                "preserve_tables": preserve_tables,
                "enable_ocr": enable_ocr,
                "table_mode": table_mode
            }
        )
        
        if process_immediately:
            await self.process_document(document_id)
            doc_info = await vector_store.get_document(document_id)
        
        return doc_info
    
    async def upload_url(self, url: str) -> Dict[str, Any]:
        """Process a URL and add to knowledge base."""
        skip_duplicates = os.getenv("SKIP_DUPLICATE_INGEST", "0").strip().lower() in {"1", "true", "yes", "y"}
        vector_store = await get_vector_store()
        if skip_duplicates:
            existing = await vector_store.find_document_by_source_url(url)
            if existing:
                if existing.get("status") != "processed":
                    await self.process_document(existing["document_id"])
                    refreshed = await vector_store.get_document(existing["document_id"])
                    return refreshed or existing
                return existing
        
        download = get_file_service().download_file(url)
        file_path = Path(download.file_path)
        filename = file_path.name
        content_hash = hashlib.md5(file_path.read_bytes()).hexdigest()
        document_id = self._generate_document_id(url, content_hash)

        doc_info = await vector_store.add_document(
            document_id=document_id,
            filename=filename,
            file_path=str(file_path),
            source_type="url",
            mime_type="application/pdf",
            file_size=file_path.stat().st_size,
            metadata={"source_url": url}
        )
        
        await self.process_document(document_id)
        
        return await vector_store.get_document(document_id)
    
    async def process_document(self, document_id: str) -> Dict[str, Any]:
        """
        Process a document via RagEngine (KETJU ingestion).
        
        Args:
            document_id: The document ID to process
            
        Returns:
            Processing result info
        """
        vector_store = await get_vector_store()
        doc = await vector_store.get_document(document_id)
        
        if not doc:
            raise ValueError(f"Document not found: {document_id}")
        
        file_path = doc.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise ValueError(f"File not found: {file_path}")

        await vector_store.update_document_status(document_id, "processing")
        await vector_store.delete_rag_chunks(document_id, file_path, doc.get("filename"))

        rag = get_rag_engine()
        chunk_count = rag.ingest(files=[file_path], document_ids=[document_id])

        await vector_store.update_document_status(document_id, "processed", chunk_count=chunk_count)

        return {
            "document_id": document_id,
            "filename": doc["filename"],
            "status": "processed",
            "chunks": chunk_count,
        }
    
    async def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents from the documents registry table."""
        vector_store = await get_vector_store()
        rows = await vector_store.list_documents()
        return [
            {
                "document_id": r["document_id"],
                "filename": r["filename"],
                "node_count": r.get("chunk_count") or 0,
                "status": r.get("status"),
            }
            for r in rows
        ]

    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a single document by ID from the documents registry table."""
        vector_store = await get_vector_store()
        return await vector_store.get_document(document_id)
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its chunks."""
        vector_store = await get_vector_store()
        
        doc = await vector_store.get_document(document_id)
        if doc and doc.get("file_path"):
            file_path = Path(doc["file_path"])
            if file_path.exists():
                file_path.unlink()
        
        return await vector_store.delete_document(document_id)
    
    async def reset_knowledge_base(self) -> Dict[str, int]:
        """Reset the entire knowledge base."""
        vector_store = await get_vector_store()
        db_result = await vector_store.reset()
        file_result = get_file_service().reset_storage()
        return {**db_result, **file_result}
    
    async def reingest_all(self) -> Dict[str, Any]:
        """Re-process all documents."""
        vector_store = await get_vector_store()
        docs = await vector_store.list_documents()
        
        results = {"processed": 0, "failed": 0, "errors": []}
        
        for doc in docs:
            try:
                await self.process_document(doc["document_id"])
                results["processed"] += 1
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({"document_id": doc["document_id"], "error": str(e)})
        
        return results
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Search the knowledge base, optionally filtered by document."""
        rag = get_rag_engine()
        retrieved = rag.query_handler.retrieve(
            rag,
            query,
            document_id=document_id,
            document_ids=document_ids,
            top_k=top_k,
        )

        retrieval_id = create_retrieval_id()
        trace_id = get_current_trace_id()

        chunks: List[Dict[str, Any]] = []
        for rank, result in enumerate(retrieved, start=1):
            node = result.node
            metadata = dict(node.metadata or {})
            doc_id = document_id or metadata.get('document_id')
            filename = metadata.get('filename') or metadata.get('file_name')
            score = float(result.score or 0.0)

            chunks.append(
                build_retrieved_chunk(
                    chunk_id=node.node_id,
                    content=node.get_content(),
                    metadata=metadata,
                    score=score,
                    rank=rank,
                    query=query,
                    top_k=top_k,
                    retrieval_id=retrieval_id,
                    collection_name=f'{self.settings.ketju_schema_name}.data_{self.settings.ketju_table_name}',
                    document_id=doc_id,
                    filename=filename,
                    trace_id=trace_id,
                )
            )

        return chunks
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics."""
        vector_store = await get_vector_store()
        return await vector_store.get_stats()


# Singleton instance
_document_service: Optional[DocumentService] = None

async def get_document_service() -> DocumentService:
    """Get or create the document service singleton."""
    global _document_service
    if _document_service is None:
        _document_service = DocumentService()
    return _document_service
