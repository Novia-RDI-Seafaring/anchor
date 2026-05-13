"""Workspace lifecycle + state."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from anchor.adapters.http.deps import get_workspace_service
from anchor.adapters.http.schemas import CreateWorkspaceRequest, SnapshotRequest
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


@router.post("/{slug}/snapshot")
async def snapshot(
    slug: str,
    req: SnapshotRequest | None = None,
    svc: WorkspaceService = Depends(get_workspace_service),
):
    """Render the workspace canvas to an image and stream the bytes back.

    A POST (not GET) because each call has side-effects: the wired
    snapshotter writes a timestamped file to disk so successive captures
    form a timeline. The response body is the raw image bytes; clients
    that want the on-disk path should call the CLI / MCP instead.
    """
    req = req or SnapshotRequest()
    try:
        result = await svc.snapshot(
            slug,
            format=req.format,
            viewport=req.viewport,
            full_page=req.full_page,
        )
    except RuntimeError as e:
        # No snapshotter wired (dev served without playwright). 501 makes
        # it obvious this isn't a missing-workspace problem.
        raise HTTPException(501, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except NotImplementedError as e:
        raise HTTPException(501, str(e))

    if result.path is not None:
        return FileResponse(result.path, media_type=result.content_type)
    assert result.bytes_ is not None
    return Response(content=result.bytes_, media_type=result.content_type)
