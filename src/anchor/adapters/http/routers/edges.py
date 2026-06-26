"""Edge CRUD on a workspace."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from anchor.adapters.http.deps import get_workspace_service
from anchor.adapters.http.schemas import AddEdgeRequest, UpdateEdgeRequest
from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.workspace.workspace import CommandError

router = APIRouter(prefix="/api/workspaces", tags=["edges"])


@router.post("/{slug}/edges", status_code=201)
async def add_edge(slug: str, req: AddEdgeRequest, svc: WorkspaceService = Depends(get_workspace_service)):
    kwargs = req.model_dump(exclude_none=True)
    # `edge_type` is canonical; accept `type` as an alias and default (#186).
    edge_type = kwargs.pop("edge_type", None) or kwargs.pop("type", None) or "floating"
    kwargs.pop("type", None)
    kwargs["edge_type"] = edge_type
    try:
        state, env = await svc.add_edge(slug, **kwargs)
    except CommandError as e:
        raise HTTPException(400, str(e))
    return {"event": env.model_dump(), "state": state.get_state()}


@router.patch("/{slug}/edges/{edge_id}")
async def update_edge(
    slug: str,
    edge_id: str,
    req: UpdateEdgeRequest,
    svc: WorkspaceService = Depends(get_workspace_service),
):
    fields = req.model_dump(exclude_none=True)
    # `type` is an alias for `edge_type` (#186); canonical wins if both set.
    if "type" in fields:
        fields.setdefault("edge_type", fields.pop("type"))
        fields.pop("type", None)
    try:
        state, env = await svc.update_edge(slug, edge_id, fields)
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
