"""Workspace lifecycle + state."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from anchor.adapters.http.deps import get_workspace_service
from anchor.adapters.http.schemas import CreateWorkspaceRequest
from anchor.core.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("")
async def list_workspaces(svc: WorkspaceService = Depends(get_workspace_service)):
    return await svc.list_workspaces()


@router.post("", status_code=201)
async def create_workspace(req: CreateWorkspaceRequest, svc: WorkspaceService = Depends(get_workspace_service)):
    return await svc.create_workspace(req.slug, title=req.title)


@router.get("/{slug}/state")
async def get_state(slug: str, svc: WorkspaceService = Depends(get_workspace_service)):
    state = await svc.get_state(slug)
    if state is None:
        raise HTTPException(404, f"workspace {slug!r} not found")
    return state


@router.post("/{slug}/clear")
async def clear(slug: str, svc: WorkspaceService = Depends(get_workspace_service)):
    state, env = await svc.clear(slug)
    return {"version": env.version, "state": state.get_state()}
