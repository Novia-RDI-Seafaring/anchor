"""
Document Service.

Orchestrates document lifecycle: upload → ingest → search → delete.
"""

import os
import hashlib
import threading
import aiofiles
from typing import Optional, Dict, Any, List
from pathlib import Path

from ..core.config import get_settings
from ..api.file_service import get_file_service
from .vector_store import get_vector_store


# ---------------------------------------------------------------------------
# In-memory pipeline progress tracker
# ---------------------------------------------------------------------------
_pipeline_jobs: Dict[str, Dict[str, Any]] = {}   # filename -> status dict
_pipeline_lock = threading.Lock()


def _update_pipeline_status(filename: str, stage: str, current: int, total: int) -> None:
    with _pipeline_lock:
        _pipeline_jobs[filename] = {
            "stage": stage,
            "current": current,
            "total": total,
        }
        if stage == "done":
            # Keep for a short while so the frontend can see "done"
            pass


def get_pipeline_status(filename: str) -> Optional[Dict[str, Any]]:
    with _pipeline_lock:
        return _pipeline_jobs.get(filename)


def clear_pipeline_status(filename: str) -> None:
    with _pipeline_lock:
        _pipeline_jobs.pop(filename, None)


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
        Process a document through Anchor's ingestion pipeline.

        Runs the full pipeline (silver + gold) in a background thread so the
        HTTP response returns immediately.  The document status is updated
        in the DB as stages complete.
        """
        vector_store = await get_vector_store()
        doc = await vector_store.get_document(document_id)

        if not doc:
            raise ValueError(f"Document not found: {document_id}")

        file_path = doc.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise ValueError(f"File not found: {file_path}")

        await vector_store.update_document_status(document_id, "processing")

        # Clean up any legacy KETJU chunks
        await vector_store.delete_rag_chunks(document_id, file_path, doc.get("filename"))

        # Run entire pipeline in background thread
        self._run_pipeline_bg(document_id, Path(file_path))

        return {
            "document_id": document_id,
            "filename": doc["filename"],
            "status": "processing",
        }

    def _run_pipeline_bg(self, document_id: str, file_path: Path) -> None:
        """Run the full pipeline (silver + gold) in a background thread."""
        import asyncio
        filename = file_path.name

        def _on_progress(stage: str, current: int, total: int) -> None:
            _update_pipeline_status(filename, stage, current, total)

        def _run() -> None:
            try:
                import json as _json
                import asyncio
                from ..ingestion.pipeline import run_silver_pipeline, run_full_pipeline
                from ..agent.tools.product_data import _refresh_data_dir

                _update_pipeline_status(filename, "docling", 0, 0)

                # Silver (deterministic: docling + index + pages + md)
                data_dir = self.settings.data_dir
                silver_dir = run_silver_pipeline(file_path, data_dir)

                # Update document status with page count
                index_path = silver_dir / "index.json"
                page_count = 0
                if index_path.exists():
                    index = _json.loads(index_path.read_text())
                    page_count = index.get("document", {}).get("page_count", 0)

                loop = asyncio.new_event_loop()
                try:
                    vs = loop.run_until_complete(get_vector_store())
                    loop.run_until_complete(
                        vs.update_document_status(document_id, "processed", chunk_count=page_count)
                    )
                finally:
                    loop.close()

                # Gold (LLM polish + regions) with progress
                _update_pipeline_status(filename, "polishing", 0, page_count)
                run_full_pipeline(file_path, data_dir, on_progress=_on_progress)
                _refresh_data_dir()

            except Exception:
                _update_pipeline_status(filename, "error", 0, 0)
                import traceback
                traceback.print_exc()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
    
    def run_full_pipeline(
        self,
        file_path: Path,
        filename: str,
        *,
        polish: bool = True,
        regions: bool = True,
        model: str = "gpt-5.4",
    ) -> Dict[str, Any]:
        """Run the full ingestion pipeline (silver + gold) for a single document.

        Returns a summary of what was produced.
        """
        from ..ingestion.pipeline import run_full_pipeline
        from ..agent.tools.product_data import _refresh_data_dir

        data_dir = self.settings.data_dir
        result = run_full_pipeline(
            file_path, data_dir, polish=polish, regions=regions, model=model,
        )
        _refresh_data_dir()
        return result

    async def run_pipeline_for_document(
        self,
        document_id: str,
        *,
        polish: bool = True,
        regions: bool = True,
        model: str = "gpt-5.4",
    ) -> Dict[str, Any]:
        """Run full pipeline for a document by ID."""
        vector_store = await get_vector_store()
        doc = await vector_store.get_document(document_id)
        if not doc:
            raise ValueError(f"Document not found: {document_id}")

        file_path = doc.get("file_path")
        if not file_path or not os.path.exists(file_path):
            raise ValueError(f"File not found: {file_path}")

        return self.run_full_pipeline(
            Path(file_path),
            doc.get("filename", ""),
            polish=polish,
            regions=regions,
            model=model,
        )

    async def run_pipeline_all(
        self,
        *,
        polish: bool = True,
        regions: bool = True,
        model: str = "gpt-5.4",
    ) -> Dict[str, Any]:
        """Run full pipeline for all documents."""
        vector_store = await get_vector_store()
        docs = await vector_store.list_documents()
        results = {"processed": 0, "failed": 0, "details": []}

        for doc in docs:
            file_path = doc.get("file_path")
            if not file_path or not os.path.exists(file_path):
                results["failed"] += 1
                results["details"].append({
                    "document_id": doc["document_id"],
                    "error": f"file not found: {file_path}",
                })
                continue
            try:
                detail = self.run_full_pipeline(
                    Path(file_path),
                    doc.get("filename", ""),
                    polish=polish,
                    regions=regions,
                    model=model,
                )
                detail["document_id"] = doc["document_id"]
                results["processed"] += 1
                results["details"].append(detail)
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "document_id": doc["document_id"],
                    "error": str(e),
                })

        return results

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
        """Search the knowledge base using the pre-computed query index.

        Falls back to empty results if the query index hasn't been built yet.
        """
        from ..ingestion.query_index import load_query_index, search_queries

        data_dir = self.settings.data_dir
        index = load_query_index(data_dir)
        if not index:
            return []

        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.embeddings.create(
                model="text-embedding-3-large", input=[query],
            )
            query_vector = response.data[0].embedding
        except Exception:
            return []

        results = search_queries(index, query_vector, top_k=top_k)

        # Filter by document if requested
        if document_id or document_ids:
            vector_store = await get_vector_store()
            # Resolve document_id(s) to filenames for filtering
            filter_filenames: set[str] = set()
            ids_to_check = [document_id] if document_id else (document_ids or [])
            for did in ids_to_check:
                doc = await vector_store.get_document(did)
                if doc:
                    filter_filenames.add(doc.get("filename", ""))
            if filter_filenames:
                results = [
                    r for r in results
                    if any(fn in (r.get("doc_slug") or "") for fn in filter_filenames)
                ]

        chunks: List[Dict[str, Any]] = []
        for rank, r in enumerate(results[:top_k], start=1):
            chunks.append({
                "content": r.get("global_answer") or r.get("query", ""),
                "metadata": {
                    "query": r.get("query"),
                    "topic": r.get("topic"),
                    "doc_slug": r.get("doc_slug"),
                    "page": r.get("page"),
                    "region_id": r.get("region_id"),
                },
                "similarity": r.get("score", 0.0),
                "rank": rank,
            })

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
