"""Knowledge snippet persistence API."""
import json
from typing import Any, List

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from ..knowledge_base.vector_store import get_vector_store
from ..core.config import get_settings

router = APIRouter(prefix="/api/snippets", tags=["snippets"])


async def _pool():
    vs = await get_vector_store()
    return vs.pool


class CreateSnippetRequest(BaseModel):
    id: str
    name: str = "Snippet"
    nodes: List[Any] = []
    relations: List[Any] = []


@router.get("")
async def list_snippets(x_user_id: str = Header(default="")):
    schema = get_settings().db_schema
    pool = await _pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT id, name, nodes, relations, created_at
            FROM "{schema}".knowledge_snippets
            WHERE user_id = $1
            ORDER BY created_at DESC
        """, x_user_id)
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "nodes": json.loads(r["nodes"]) if isinstance(r["nodes"], str) else r["nodes"],
            "relations": json.loads(r["relations"]) if isinstance(r["relations"], str) else r["relations"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.post("")
async def create_snippet(req: CreateSnippetRequest, x_user_id: str = Header(default="")):
    schema = get_settings().db_schema
    pool = await _pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"""
            INSERT INTO "{schema}".knowledge_snippets (id, user_id, name, nodes, relations)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, nodes = EXCLUDED.nodes,
                relations = EXCLUDED.relations
            RETURNING id, name, created_at
        """, req.id, x_user_id, req.name, json.dumps(req.nodes), json.dumps(req.relations))
    return dict(row)


@router.delete("/{snippet_id}")
async def delete_snippet(snippet_id: str, x_user_id: str = Header(default="")):
    schema = get_settings().db_schema
    pool = await _pool()
    async with pool.acquire() as conn:
        result = await conn.execute(f"""
            DELETE FROM "{schema}".knowledge_snippets WHERE id = $1 AND user_id = $2
        """, snippet_id, x_user_id)
    if result != "DELETE 1":
        raise HTTPException(status_code=404, detail="Snippet not found")
    return {"success": True}
