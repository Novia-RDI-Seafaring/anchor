"""Conversation persistence API."""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

from ..knowledge_base.conversation_store import get_conversation_store

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    id: str
    title: str = "New Conversation"


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    messages: Optional[Any] = None
    canvas_state: Optional[Dict[str, Any]] = None


@router.get("")
async def list_conversations(x_user_id: str = Header(default="")):
    store = await get_conversation_store()
    return await store.list_conversations(user_id=x_user_id)


@router.post("")
async def create_conversation(req: CreateConversationRequest, x_user_id: str = Header(default="")):
    store = await get_conversation_store()
    return await store.create_conversation(req.id, req.title, user_id=x_user_id)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, x_user_id: str = Header(default="")):
    store = await get_conversation_store()
    conv = await store.get_conversation(conversation_id, user_id=x_user_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.put("/{conversation_id}")
async def update_conversation(conversation_id: str, req: UpdateConversationRequest, x_user_id: str = Header(default="")):
    store = await get_conversation_store()
    result = await store.update_conversation(
        conversation_id,
        user_id=x_user_id,
        title=req.title,
        messages=req.messages,
        canvas_state=req.canvas_state,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return result


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, x_user_id: str = Header(default="")):
    store = await get_conversation_store()
    deleted = await store.delete_conversation(conversation_id, user_id=x_user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True}
