"""Conversation persistence — JSON-file-backed, no database required."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import get_settings


class ConversationStore:
    """CRUD for conversations, stored as individual JSON files."""

    def __init__(self) -> None:
        settings = get_settings()
        self._dir = settings.data_dir / "store" / "conversations"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, conversation_id: str) -> Path:
        # Sanitise to avoid path traversal
        safe = conversation_id.replace("/", "_").replace("..", "_")
        return self._dir / f"{safe}.json"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _read(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        p = self._path(conversation_id)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _write(self, conv: Dict[str, Any]) -> None:
        p = self._path(conv["id"])
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(conv, indent=2, default=str), encoding="utf-8")
        tmp.replace(p)

    # ------------------------------------------------------------------

    async def list_conversations(self, user_id: str = "") -> List[Dict[str, Any]]:
        with self._lock:
            result = []
            for f in sorted(self._dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    conv = json.loads(f.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                if conv.get("user_id", "") != user_id:
                    continue
                result.append({
                    "id": conv["id"],
                    "title": conv.get("title", ""),
                    "created_at": conv.get("created_at"),
                    "updated_at": conv.get("updated_at"),
                    "message_count": len(conv.get("messages") or []),
                })
            return result

    async def get_conversation(self, conversation_id: str, user_id: str = "") -> Optional[Dict[str, Any]]:
        with self._lock:
            conv = self._read(conversation_id)
        if not conv:
            return None
        if conv.get("user_id", "") != user_id:
            return None
        return conv

    async def create_conversation(
        self,
        conversation_id: str,
        title: str = "New Conversation",
        user_id: str = "",
    ) -> Dict[str, Any]:
        now = self._now()
        conv: Dict[str, Any] = {
            "id": conversation_id,
            "title": title,
            "user_id": user_id,
            "messages": [],
            "canvas_state": {},
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            existing = self._read(conversation_id)
            if existing:
                existing["updated_at"] = now
                self._write(existing)
                return existing
            self._write(conv)
        return conv

    async def update_conversation(
        self,
        conversation_id: str,
        *,
        user_id: str = "",
        title: Optional[str] = None,
        messages: Optional[Any] = None,
        canvas_state: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock:
            conv = self._read(conversation_id)
            if not conv:
                # Auto-create (matches old Postgres ON CONFLICT behaviour)
                conv = {
                    "id": conversation_id,
                    "title": title or "New Conversation",
                    "user_id": user_id,
                    "messages": [],
                    "canvas_state": {},
                    "created_at": self._now(),
                    "updated_at": self._now(),
                }
            if conv.get("user_id", "") != user_id:
                return None
            if title is not None:
                conv["title"] = title
            if messages is not None:
                conv["messages"] = messages
            if canvas_state is not None:
                conv["canvas_state"] = canvas_state
            conv["updated_at"] = self._now()
            self._write(conv)
        return {"id": conv["id"], "title": conv["title"], "created_at": conv.get("created_at"), "updated_at": conv["updated_at"]}

    async def delete_conversation(self, conversation_id: str, user_id: str = "") -> bool:
        with self._lock:
            conv = self._read(conversation_id)
            if not conv or conv.get("user_id", "") != user_id:
                return False
            p = self._path(conversation_id)
            p.unlink(missing_ok=True)
            return True


_store: Optional[ConversationStore] = None


async def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store
