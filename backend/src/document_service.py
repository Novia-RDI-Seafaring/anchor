"""
Document Service.

Orchestrates document processing: upload -> Docling conversion -> chunking -> embedding -> storage.
"""

import os
import hashlib
import aiofiles
from typing import Optional, Dict, Any, List
from pathlib import Path

from .config import get_settings
from .vector_store import get_vector_store
from .embeddings import get_embeddings_service
from .docling_processing.docling_converter import DoclingConverter
from .docling_processing.formatters import MarkdownFormatter
from .page_image_service import get_page_image_service


class DocumentService:
    """Service for document ingestion and management."""
    
    def __init__(self):
        self.settings = get_settings()
        self.uploads_dir = Path(self.settings.uploads_dir).resolve()
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize Docling converter
        self.converter = DoclingConverter(
            preserve_images=False,  # Faster processing
            preserve_tables=True,
            enable_ocr=False,
            table_mode="fast"
        )
        self.formatter = MarkdownFormatter()
    
    def _generate_document_id(self, filename: str, content_hash: Optional[str] = None) -> str:
        """Generate a unique document ID."""
        base = f"{filename}-{content_hash or ''}"
        return hashlib.md5(base.encode()).hexdigest()[:12]
    
    async def upload_file(
        self,
        filename: str,
        content: bytes,
        process_immediately: bool = True
    ) -> Dict[str, Any]:
        """
        Upload and optionally process a file.
        
        Args:
            filename: Original filename
            content: File content as bytes
            process_immediately: Whether to process right away
            
        Returns:
            Document info dict
        """
        # Save file to uploads directory
        file_path = self.uploads_dir / filename
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Generate document ID
        content_hash = hashlib.md5(content).hexdigest()
        document_id = self._generate_document_id(filename, content_hash)
        
        # Get vector store and add document record
        vector_store = await get_vector_store()
        
        # Determine mime type
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
            metadata={"content_hash": content_hash}
        )
        
        # Process if requested
        if process_immediately:
            await self.process_document(document_id)
            doc_info = await vector_store.get_document(document_id)
        
        return doc_info
    
    async def upload_url(self, url: str) -> Dict[str, Any]:
        """
        Process a URL and add to knowledge base.
        
        Args:
            url: URL to process
            
        Returns:
            Document info dict
        """
        import httpx
        
        # Fetch URL content
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            content = response.content
        
        # Generate document ID from URL
        document_id = self._generate_document_id(url, hashlib.md5(content).hexdigest())
        
        # Determine filename from URL
        from urllib.parse import urlparse
        parsed = urlparse(url)
        filename = Path(parsed.path).name or "webpage.html"
        if not Path(filename).suffix:
            filename += ".html"
        
        # Save content
        file_path = self.uploads_dir / f"{document_id}_{filename}"
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Add to vector store
        vector_store = await get_vector_store()
        doc_info = await vector_store.add_document(
            document_id=document_id,
            filename=filename,
            file_path=str(file_path),
            source_type="url",
            mime_type=response.headers.get("content-type", "text/html"),
            file_size=len(content),
            metadata={"source_url": url}
        )
        
        # Process the document
        await self.process_document(document_id)
        
        return await vector_store.get_document(document_id)
    
    async def process_document(self, document_id: str) -> Dict[str, Any]:
        """
        Process a document: convert with Docling, chunk, embed, store.
        
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
        
        print(f"DocumentService: Processing {doc['filename']}...")
        
        # Convert with Docling
        try:
            conversion_result = self.converter.convert_document(file_path)
            
            # Get chunks using HybridChunker
            chunks = self.formatter.create_chunks(
                conversion_result, 
                chunk_size=self.settings.chunk_size
            )
            
            print(f"DocumentService: Created {len(chunks)} chunks")
            
        except Exception as e:
            print(f"DocumentService: Docling failed, using fallback: {e}")
            # Fallback: read as text and create simple chunks
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
            
            # Simple chunking fallback
            chunk_size = self.settings.chunk_size * 4  # Approximate chars per token
            chunks = []
            for i in range(0, len(content), chunk_size):
                chunks.append({
                    "content": content[i:i + chunk_size],
                    "metadata": {"chunk_type": "fallback", "chunk_index": len(chunks)}
                })
        
        if not chunks:
            return {"document_id": document_id, "status": "no_content", "chunks": 0}
        
        # Generate embeddings
        embeddings_service = get_embeddings_service()
        texts = [chunk["content"] for chunk in chunks]
        
        print(f"DocumentService: Generating embeddings for {len(texts)} chunks...")
        embeddings = embeddings_service.embed_texts(texts)
        
        # Store in vector database
        chunk_count = await vector_store.add_chunks(document_id, chunks, embeddings)
        
        print(f"DocumentService: Stored {chunk_count} chunks for {doc['filename']}")
        
        # Generate and store page images for PDF files
        page_count = 0
        if file_path.lower().endswith('.pdf'):
            try:
                print(f"DocumentService: Generating page images for {doc['filename']}...")
                page_image_service = get_page_image_service()
                page_images = page_image_service.generate_page_images(file_path)
                page_count = await vector_store.add_page_images(document_id, page_images)
                print(f"DocumentService: Stored {page_count} page images")
            except Exception as e:
                print(f"DocumentService: Failed to generate page images: {e}")
        
        return {
            "document_id": document_id,
            "filename": doc["filename"],
            "status": "processed",
            "chunks": chunk_count,
            "pages": page_count
        }
    
    async def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents."""
        vector_store = await get_vector_store()
        return await vector_store.list_documents()
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and its chunks."""
        vector_store = await get_vector_store()
        
        # Get document to find file path
        doc = await vector_store.get_document(document_id)
        if doc and doc.get("file_path"):
            file_path = Path(doc["file_path"])
            if file_path.exists():
                file_path.unlink()
        
        return await vector_store.delete_document(document_id)
    
    async def reset_knowledge_base(self) -> Dict[str, int]:
        """Reset the entire knowledge base."""
        vector_store = await get_vector_store()
        return await vector_store.reset()
    
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
    
    async def search(self, query: str, top_k: int = 5, document_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search the knowledge base, optionally filtered by document.
        
        Args:
            query: Search query
            top_k: Number of results
            document_id: Optional document ID to filter search
            
        Returns:
            List of matching chunks with metadata
        """
        embeddings_service = get_embeddings_service()
        query_embedding = embeddings_service.embed_text(query)
        
        vector_store = await get_vector_store()
        return await vector_store.search(query_embedding, top_k=top_k, document_id=document_id)
    
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

