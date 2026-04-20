"""Document registry — JSON-file-backed, no database required."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import get_settings


class VectorStore:
    """Document registry backed by a JSON file."""

    def __init__(self) -> None:
        settings = get_settings()
        self._store_dir = settings.data_dir / "store"
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._store_dir / "documents.json"
        self._lock = threading.Lock()
        self._docs: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._docs = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._docs = []
        else:
            self._docs = []

    def _save(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._docs, indent=2, default=str), encoding="utf-8")
        tmp.replace(self._path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # Compatibility stubs (callers that referenced the old pg interface)
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """No-op — file store is ready immediately."""
        pass

    async def delete_rag_chunks(
        self,
        document_id: str,
        file_path: str | None = None,
        filename: str | None = None,
    ) -> None:
        """No-op — legacy KETJU chunk cleanup."""
        pass

    # ------------------------------------------------------------------
    # Document CRUD
    # ------------------------------------------------------------------

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
        now = self._now()
        doc: Dict[str, Any] = {
            "document_id": document_id,
            "filename": filename,
            "file_path": file_path,
            "source_type": source_type,
            "mime_type": mime_type,
            "file_size": file_size,
            "chunk_count": 0,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
        }
        with self._lock:
            self._docs.append(doc)
            self._save()
        return doc

    async def find_document_by_content_hash(self, content_hash: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for doc in self._docs:
                meta = doc.get("metadata") or {}
                if meta.get("content_hash") == content_hash:
                    return dict(doc)
        return None

    async def find_document_by_source_url(self, url: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for doc in self._docs:
                meta = doc.get("metadata") or {}
                if meta.get("source_url") == url:
                    return dict(doc)
        return None

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        chunk_count: Optional[int] = None,
    ) -> None:
        with self._lock:
            for doc in self._docs:
                if doc["document_id"] == document_id:
                    doc["status"] = status
                    doc["updated_at"] = self._now()
                    if chunk_count is not None:
                        doc["chunk_count"] = chunk_count
                    break
            self._save()

    async def list_documents(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(d) for d in self._docs]

    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for doc in self._docs:
                if doc["document_id"] == document_id:
                    return dict(doc)
        return None

    async def delete_document(self, document_id: str) -> bool:
        with self._lock:
            before = len(self._docs)
            self._docs = [d for d in self._docs if d["document_id"] != document_id]
            if len(self._docs) < before:
                self._save()
                return True
        return False

    async def reset(self) -> Dict[str, int]:
        with self._lock:
            count = len(self._docs)
            self._docs = []
            self._save()
        return {"documents_deleted": count}

    async def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total = len(self._docs)
            processed = sum(1 for d in self._docs if d.get("status") == "processed")
        return {
            "total_documents": total,
            "processed_documents": processed,
            "status": "file-backed",
        }

    async def close(self) -> None:
        pass


_vector_store: Optional[VectorStore] = None


async def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
