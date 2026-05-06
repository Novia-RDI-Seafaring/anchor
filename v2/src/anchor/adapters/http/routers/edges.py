"""Edge CRUD on a workspace."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from anchor.adapters.http.deps import get_workspace_service
from anchor.adapters.http.schemas import AddEdgeRequest
from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.workspace.workspace import CommandError

router = APIRouter(prefix="/api/workspaces", tags=["edges"])


@router.post("/{slug}/edges", status_code=201)
async def add_edge(slug: str, req: AddEdgeRequest, svc: WorkspaceService = Depends(get_workspace_service)):
    try:
        kwargs = req.model_dump(exclude_none=True)
        state, env = await svc.add_edge(slug, **kwargs)
    except CommandError as e:
        raise HTTPException(400, str(e))
    return {"event": env.model_dump(), "state": state.get_state()}


@router.delete("/{slug}/edges/{edge_id}")
async def remove_edge(slug: str, edge_id: str, svc: WorkspaceService = Depends(get_workspace_service)):
    try:
        state, env = await svc.remove_edge(slug, edge_id)
    except CommandError as e:
        raise HTTPException(400, str(e))
    return {"event": env.model_dump(), "state": state.get_state()}
