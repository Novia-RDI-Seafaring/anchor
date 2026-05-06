"""Node CRUD on a workspace."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from anchor.adapters.http.deps import get_workspace_service
from anchor.adapters.http.schemas import AddNodeRequest, UpdateNodeRequest
from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.workspace.workspace import CommandError

router = APIRouter(prefix="/api/workspaces", tags=["nodes"])


@router.post("/{slug}/nodes", status_code=201)
async def add_node(slug: str, req: AddNodeRequest, svc: WorkspaceService = Depends(get_workspace_service)):
    try:
        kwargs = req.model_dump(exclude_none=True)
        state, env = await svc.add_node(slug, **kwargs)
    except CommandError as e:
        raise HTTPException(400, str(e))
    return {"event": env.model_dump(), "state": state.get_state()}


@router.patch("/{slug}/nodes/{node_id}")
async def update_node(slug: str, node_id: str, req: UpdateNodeRequest, svc: WorkspaceService = Depends(get_workspace_service)):
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        if {"x", "y"} <= fields.keys() and len(fields) == 2:
            state, env = await svc.move_node(slug, node_id, fields["x"], fields["y"])
        else:
            state, env = await svc.update_node(slug, node_id, fields)
    except CommandError as e:
        raise HTTPException(400, str(e))
    return {"event": env.model_dump(), "state": state.get_state()}


@router.delete("/{slug}/nodes/{node_id}")
async def remove_node(slug: str, node_id: str, svc: WorkspaceService = Depends(get_workspace_service)):
    try:
        state, envelopes = await svc.remove_node(slug, node_id)
    except CommandError as e:
        raise HTTPException(400, str(e))
    return {"events": [e.model_dump() for e in envelopes], "state": state.get_state()}
