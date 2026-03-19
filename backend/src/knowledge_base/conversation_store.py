"""Conversation persistence — messages + canvas state stored in Postgres."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..core.config import get_settings
from .vector_store import get_vector_store  # reuses the same asyncpg pool


class ConversationStore:
    """CRUD for the anchor.conversations table."""

    def __init__(self, schema: str) -> None:
        self._schema = schema

    async def _pool(self):
        vs = await get_vector_store()
        return vs.pool

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """Return conversations for a user ordered newest-first (no messages payload)."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, title, created_at, updated_at,
                       jsonb_array_length(messages) AS message_count
                FROM "{self._schema}".conversations
                WHERE user_id = $1
                ORDER BY updated_at DESC
            """, user_id)
        return [dict(r) for r in rows]

    async def get_conversation(self, conversation_id: str, user_id: str = "") -> Optional[Dict[str, Any]]:
        pool = await self._pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"""
                SELECT id, title, messages, canvas_state, created_at, updated_at
                FROM "{self._schema}".conversations
                WHERE id = $1 AND user_id = $2
            """, conversation_id, user_id)
        if not row:
            return None
        result = dict(row)
        result["messages"] = json.loads(result["messages"]) if isinstance(result["messages"], str) else result["messages"]
        result["canvas_state"] = json.loads(result["canvas_state"]) if isinstance(result["canvas_state"], str) else result["canvas_state"]
        return result

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create_conversation(self, conversation_id: str, title: str = "New Conversation", user_id: str = "") -> Dict[str, Any]:
        pool = await self._pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"""
                INSERT INTO "{self._schema}".conversations (id, title, user_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                RETURNING id, title, created_at, updated_at
            """, conversation_id, title, user_id)
        return dict(row)

    async def update_conversation(
        self,
        conversation_id: str,
        *,
        user_id: str = "",
        title: Optional[str] = None,
        messages: Optional[Any] = None,
        canvas_state: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """Upsert fields that are provided (None = keep existing)."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            # Build update dynamically so we only touch provided fields
            sets = ["updated_at = CURRENT_TIMESTAMP"]
            params: list[Any] = [conversation_id]

            if title is not None:
                params.append(title)
                sets.append(f"title = ${len(params)}")
            if messages is not None:
                params.append(json.dumps(messages))
                sets.append(f"messages = ${len(params)}::jsonb")
            if canvas_state is not None:
                params.append(json.dumps(canvas_state))
                sets.append(f"canvas_state = ${len(params)}::jsonb")

            params.append(user_id)
            row = await conn.fetchrow(f"""
                UPDATE "{self._schema}".conversations
                SET {', '.join(sets)}
                WHERE id = $1 AND user_id = ${len(params)}
                RETURNING id, title, created_at, updated_at
            """, *params)
        return dict(row) if row else None

    async def delete_conversation(self, conversation_id: str, user_id: str = "") -> bool:
        pool = await self._pool()
        async with pool.acquire() as conn:
            result = await conn.execute(f"""
                DELETE FROM "{self._schema}".conversations WHERE id = $1 AND user_id = $2
            """, conversation_id, user_id)
        return result == "DELETE 1"


_store: Optional[ConversationStore] = None


async def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        settings = get_settings()
        _store = ConversationStore(schema=settings.db_schema)
    return _store
