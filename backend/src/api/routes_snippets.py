"""Knowledge snippet persistence API — JSON-file-backed."""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from ..core.config import get_settings
from .security import require_write_access

router = APIRouter(prefix="/api/snippets", tags=["snippets"])

_lock = threading.Lock()


def _snippets_path() -> Path:
    settings = get_settings()
    d = settings.data_dir / "store"
    d.mkdir(parents=True, exist_ok=True)
    return d / "snippets.json"


def _load() -> List[dict]:
    p = _snippets_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save(data: List[dict]) -> None:
    p = _snippets_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)


class CreateSnippetRequest(BaseModel):
    id: str
    name: str = "Snippet"
    nodes: List[Any] = []
    relations: List[Any] = []


@router.get("")
async def list_snippets(x_user_id: str = Header(default="")):
    with _lock:
        snippets = _load()
    return [s for s in snippets if s.get("user_id", "") == x_user_id]


@router.post("", dependencies=[Depends(require_write_access)])
async def create_snippet(req: CreateSnippetRequest, x_user_id: str = Header(default="")):
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "id": req.id,
        "user_id": x_user_id,
        "name": req.name,
        "nodes": req.nodes,
        "relations": req.relations,
        "created_at": now,
    }
    with _lock:
        snippets = _load()
        snippets = [s for s in snippets if s["id"] != req.id]
        snippets.insert(0, entry)
        _save(snippets)
    return {"id": entry["id"], "name": entry["name"], "created_at": entry["created_at"]}


@router.delete("/{snippet_id}", dependencies=[Depends(require_write_access)])
async def delete_snippet(snippet_id: str, x_user_id: str = Header(default="")):
    with _lock:
        snippets = _load()
        before = len(snippets)
        snippets = [s for s in snippets if not (s["id"] == snippet_id and s.get("user_id", "") == x_user_id)]
        if len(snippets) == before:
            raise HTTPException(status_code=404, detail="Snippet not found")
        _save(snippets)
    return {"success": True}
