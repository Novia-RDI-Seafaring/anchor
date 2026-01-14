"""
Document Service.

Orchestrates document processing: upload -> Docling conversion -> chunking -> embedding -> storage.
"""

import os
import hashlib
import aiofiles
from typing import Optional, Dict, Any, List
from pathlib import Path

from ..core.config import get_settings
from .vector_store import get_vector_store
from .embeddings import get_embeddings_service
from .docling.converter import DoclingConverter
from .docling.formatters import MarkdownFormatter
from .images import get_page_image_service


class DocumentService:
    """Service for document ingestion and management."""
    
    def __init__(self):
        self.settings = get_settings()
        self.uploads_dir = Path(self.settings.uploads_dir).resolve()
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.formatter = MarkdownFormatter()
    
    def _generate_document_id(self, filename: str, content_hash: Optional[str] = None) -> str:
        """
        Generate a unique document ID using SHA256 for better security.
        Format: <timestamp_ms>-<hash_prefix>
        """
        from datetime import datetime
        
        # Include timestamp for uniqueness and rough chronological ordering
        timestamp_ms = int(datetime.utcnow().timestamp() * 1000)
        base = f"{filename}-{content_hash or ''}-{timestamp_ms}"
        
        # Use SHA256 instead of MD5 for better collision resistance
        hash_digest = hashlib.sha256(base.encode()).hexdigest()[:16]
        
        return f"{timestamp_ms}-{hash_digest}"
    
    def _extract_images_from_docling(self, conversion_result) -> List[Dict[str, Any]]:
        """
        Extract images (figures, diagrams) from Docling conversion result.
        
        Args:
            conversion_result: Docling conversion result object
            
        Returns:
            List of image dicts with base64 data, captions, and metadata
        """
        import base64
        import io
        
        extracted_images = []
        
        try:
            document = conversion_result.document
            
            # Iterate through document items to find pictures
            for item, level in document.iterate_items():
                # Check if item is a picture/figure
                if hasattr(item, 'label') and str(item.label).lower() in ['picture', 'figure', 'image']:
                    try:
                        # Get image data if available
                        image_data = None
                        if hasattr(item, 'image') and item.image:
                            # Convert PIL image to base64
                            pil_image = item.image.pil_image if hasattr(item.image, 'pil_image') else item.image
                            if pil_image:
                                buffer = io.BytesIO()
                                pil_image.save(buffer, format='PNG', optimize=True)
                                image_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
                                buffer.close()
                        
                        # Skip if no image data
                        if not image_data:
                            continue
                        
                        # Get caption from item text or nearby text
                        caption = item.text if hasattr(item, 'text') else None
                        
                        # Get page number and bounding box from provenance
                        page_number = None
                        bbox = None
                        if hasattr(item, 'prov') and item.prov:
                            for prov in item.prov:
                                if hasattr(prov, 'page_no'):
                                    page_number = prov.page_no
                                if hasattr(prov, 'bbox') and hasattr(prov.bbox, 'as_tuple'):
                                    bbox = {
                                        'coordinates': list(prov.bbox.as_tuple())
                                    }
                                break
                        
                        # Determine image type from label
                        image_type = 'figure'
                        label_lower = str(item.label).lower()
                        if 'diagram' in label_lower:
                            image_type = 'diagram'
                        elif 'chart' in label_lower:
                            image_type = 'chart'
                        
                        # Get dimensions
                        width = pil_image.width if pil_image else None
                        height = pil_image.height if pil_image else None
                        
                        extracted_images.append({
                            'image_type': image_type,
                            'page_number': page_number,
                            'image_base64': image_data,
                            'caption': caption,
                            'alt_text': caption,  # Use caption as alt text
                            'bbox': bbox,
                            'width': width,
                            'height': height,
                            'metadata': {
                                'label': str(item.label),
                                'level': level
                            }
                        })
                        
                    except Exception as e:
                        print(f"DocumentService: Failed to extract individual image: {e}")
                        continue
                        
        except Exception as e:
            print(f"DocumentService: Error iterating document items: {e}")
            
        return extracted_images
    
    def _extract_toc_from_docling(self, conversion_result) -> List[Dict[str, Any]]:
        """
        Extract Table of Contents from Docling conversion result.
        Primarily looks for DOCUMENT_INDEX label.
        
        Args:
            conversion_result: Docling conversion result object
            
        Returns:
            List of TOC items with text, level, and page number
        """
        toc_items = []
        try:
            from docling_core.types.doc.labels import DocItemLabel # type: ignore
            
            document = conversion_result.document
            
            # Step 1: Look for explicit DOCUMENT_INDEX items
            index_item_count = 0
            for item, level in document.iterate_items():
                if hasattr(item, 'label') and item.label == DocItemLabel.DOCUMENT_INDEX:
                    index_item_count += 1
                    page_no = None
                    if hasattr(item, 'prov') and item.prov:
                        page_no = item.prov[0].page_no if hasattr(item.prov[0], 'page_no') else None
                    
                    # Try multiple ways to extract text
                    text_content = ""
                    extraction_method = None
                    
                    # Method 1: Direct text attribute
                    if hasattr(item, 'text') and item.text:
                        text_content = item.text
                        extraction_method = "direct_text"
                    # Method 2: Try self_text if available
                    elif hasattr(item, 'self_text') and item.self_text:
                        text_content = item.self_text
                        extraction_method = "self_text"
                    # Method 3: Try to get text from children
                    elif hasattr(item, 'children') and item.children:
                        child_texts = []
                        for child in item.children:
                            if hasattr(child, 'text') and child.text:
                                child_texts.append(child.text)
                        if child_texts:
                            text_content = ' '.join(child_texts).strip()
                            extraction_method = f"children({len(child_texts)})"
                    
                    if extraction_method:
                        print(f"DocumentService: TOC item extracted via {extraction_method}: '{text_content[:50]}...' (page {page_no})")
                    else:
                        print(f"DocumentService: TOC item has NO text content (page {page_no}) - tried all methods")
                    
                    toc_items.append({
                        "text": text_content,
                        "level": level,
                        "page_no": page_no,
                        "type": "index_item"
                    })
            
            if index_item_count > 0:
                print(f"DocumentService: Found {index_item_count} DOCUMENT_INDEX items")
            
            # Step 2: If we found DOCUMENT_INDEX items but they all have empty text,
            # or if no DOCUMENT_INDEX was found, fallback to headings
            has_valid_text = any(item.get("text", "").strip() for item in toc_items)
            
            if not toc_items or not has_valid_text:
                print(f"DocumentService: TOC extraction - using heading fallback (found {len(toc_items)} DOCUMENT_INDEX items with empty text)")
                toc_items = []  # Clear empty items
                
                heading_count = 0
                for item, level in document.iterate_items():
                    # Skip if this is a table item - tables can be mislabeled as headers
                    if hasattr(item, 'label'):
                        label_str = str(item.label)
                        if 'TABLE' in label_str.upper():
                            continue  # Skip table items
                        
                        if item.label in [DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE]:
                            page_no = None
                            if hasattr(item, 'prov') and item.prov:
                                page_no = item.prov[0].page_no if hasattr(item.prov[0], 'page_no') else None
                            
                            # Use self_text first (cleaner, without children)
                            # Then fallback to text if self_text is not available
                            text_content = ""
                            if hasattr(item, 'self_text') and item.self_text:
                                text_content = item.self_text.strip()
                            elif hasattr(item, 'text') and item.text:
                                text_content = item.text.strip()
                            
                            # Filter out content that looks like tables (contains | or multiple newlines)
                            # or is too long to be a heading (>200 chars)
                            if text_content and len(text_content) <= 200:
                                # Check if it looks like table content
                                if '|' not in text_content and '\n\n' not in text_content:
                                    # Infer heading level from numbering pattern
                                    # e.g., "1." → level 1, "1.1" → level 2, "1.1.1" → level 3
                                    inferred_level = level  # Default to Docling's level
                                    
                                    # Try to extract numbered pattern at start
                                    import re
                                    number_pattern = re.match(r'^(\d+(?:\.\d+)*)', text_content.strip())
                                    if number_pattern:
                                        numbering = number_pattern.group(1)
                                        # Count dots to determine level
                                        # "1" → 0 dots → level 1
                                        # "1.1" → 1 dot → level 2
                                        # "1.1.1" → 2 dots → level 3
                                        dot_count = numbering.count('.')
                                        inferred_level = dot_count + 1
                                    
                                    heading_count += 1
                                    toc_items.append({
                                        "text": text_content,
                                        "level": inferred_level,  # Use inferred level from numbering
                                        "page_no": page_no,
                                        "type": str(item.label)
                                    })
                
                print(f"DocumentService: Extracted {heading_count} headings for TOC (filtered {heading_count} potential headings)")
                        
        except Exception as e:
            print(f"DocumentService: Error extracting TOC: {e}")
            import traceback
            traceback.print_exc()
            
        return toc_items
    
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

        # Generate content hash early so we can optionally skip duplicates across filename changes
        content_hash = hashlib.md5(content).hexdigest()

        # If enabled, skip ingest when the same bytes were already ingested (metadata.content_hash match)
        vector_store = await get_vector_store()
        if skip_duplicates:
            existing = await vector_store.find_document_by_content_hash(content_hash)
            if existing:
                # If caller wants processing and the existing doc isn't processed yet, process it now.
                if process_immediately and existing.get("status") != "processed":
                    await self.process_document(existing["document_id"])
                    refreshed = await vector_store.get_document(existing["document_id"])
                    return refreshed or existing
                return existing

        # Save file to uploads directory
        file_path = self.uploads_dir / filename
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Generate document ID
        document_id = self._generate_document_id(filename, content_hash)
        
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
            metadata={
                "content_hash": content_hash,
                "preserve_images": preserve_images,
                "preserve_tables": preserve_tables,
                "enable_ocr": enable_ocr,
                "table_mode": table_mode
            }
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
        
        # Get processing options from metadata or use defaults
        metadata = doc.get("metadata", {})
        preserve_images = metadata.get("preserve_images", True)
        preserve_tables = metadata.get("preserve_tables", True)
        enable_ocr = metadata.get("enable_ocr", False)
        table_mode = metadata.get("table_mode", "fast")
        
        # Create converter with user-specified options
        converter = DoclingConverter(
            preserve_images=preserve_images,
            preserve_tables=preserve_tables,
            enable_ocr=enable_ocr,
            table_mode=table_mode
        )
        
        # Convert with Docling
        try:
            conversion_result = converter.convert_document(file_path)
            
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
        
        # Extract and store document images (diagrams, figures) from Docling result
        image_count = 0
        toc_count = 0
        if 'conversion_result' in locals() and conversion_result:
            try:
                # Extract and store TOC
                print(f"DocumentService: Extracting TOC from {doc['filename']}...")
                toc_items = self._extract_toc_from_docling(conversion_result)
                if toc_items:
                    await vector_store.add_toc(document_id, toc_items)
                    toc_count = len(toc_items)
                    print(f"DocumentService: Stored {toc_count} TOC items")

                # Extract and store images
                print(f"DocumentService: Extracting images from {doc['filename']}...")
                extracted_images = self._extract_images_from_docling(conversion_result)
                if extracted_images:
                    image_count = await vector_store.add_document_images(document_id, extracted_images)
                    print(f"DocumentService: Stored {image_count} extracted images")
            except Exception as e:
                print(f"DocumentService: Failed to extract structural metadata: {e}")
        
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
            "pages": page_count,
            "images": image_count,
            "toc": toc_count
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
