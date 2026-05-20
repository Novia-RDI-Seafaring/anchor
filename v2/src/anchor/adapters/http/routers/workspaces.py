"""Workspace lifecycle + state."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from anchor.adapters.http.deps import get_workspace_service
from anchor.adapters.http.schemas import (
    AlignNodesRequest,
    CreateSubCanvasRequest,
    CreateWorkspaceRequest,
    DistributeNodesRequest,
    OrganizeSubtreeRequest,
    SnapshotRequest,
)
from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.workspace.workspace import CommandError

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


@router.post("/{slug}/layout")
async def organize_subtree(
    slug: str,
    req: OrganizeSubtreeRequest,
    svc: WorkspaceService = Depends(get_workspace_service),
):
    """Recompute positions for the subtree under ``root_id``.

    Body: ``{root_id, orientation, algo}``. Emits one ``NodeMoved`` per
    descendant whose position changes (the root itself is anchored).
    Response carries the resulting move list and the count of events
    appended so the client can reconcile against its own SSE feed."""
    try:
        state, envelopes = await svc.organize_subtree(
            slug, req.root_id, orientation=req.orientation, algo=req.algo,
        )
    except CommandError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    moves = [
        {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
        for env in envelopes
    ]
    return {
        "moves": moves,
        "event_count": len(envelopes),
        "state": state.get_state(),
    }


@router.post("/{slug}/align")
async def align_nodes(
    slug: str,
    req: AlignNodesRequest,
    svc: WorkspaceService = Depends(get_workspace_service),
):
    """Align the selected nodes' positions to a shared edge / midline.

    Body: ``{ids, anchor}`` where ``anchor`` is one of ``top`` / ``bottom``
    / ``left`` / ``right`` / ``center-h`` / ``center-v``. Emits one
    ``NodeMoved`` per node that genuinely moves, sharing one ``causation_id``
    so the SSE feed can group them as a single "align" gesture."""
    try:
        state, envelopes = await svc.align_nodes(slug, req.ids, req.anchor)  # type: ignore[arg-type]
    except CommandError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    moves = [
        {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
        for env in envelopes
    ]
    return {
        "moves": moves,
        "event_count": len(envelopes),
        "state": state.get_state(),
    }


@router.post("/{parent_slug}/sub-canvas", status_code=201)
async def create_sub_canvas(
    parent_slug: str,
    req: CreateSubCanvasRequest,
    svc: WorkspaceService = Depends(get_workspace_service),
):
    """Provision a child canvas and link it from the parent in one call.

    Body: ``{slug, title?, x?, y?}``. The server creates the child
    workspace (idempotent on ``slug``), then drops a ``canvas``-typed
    linking node onto ``parent_slug`` at ``(x, y)``. Returns the new
    child meta, the linking node, and the ``NodeAdded`` envelope so
    SSE consumers can reconcile.
    """
    try:
        return await svc.create_sub_canvas(
            parent_slug, req.slug, title=req.title, x=req.x, y=req.y,
        )
    except CommandError as e:
        raise HTTPException(400, str(e))


@router.post("/{slug}/distribute")
async def distribute_nodes(
    slug: str,
    req: DistributeNodesRequest,
    svc: WorkspaceService = Depends(get_workspace_service),
):
    """Distribute the selected nodes' centres evenly along ``axis``.

    Body: ``{ids, axis}`` where ``axis`` is ``horizontal`` or ``vertical``.
    Requires at least three ids; the end nodes stay put."""
    try:
        state, envelopes = await svc.distribute_nodes(slug, req.ids, req.axis)  # type: ignore[arg-type]
    except CommandError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    moves = [
        {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
        for env in envelopes
    ]
    return {
        "moves": moves,
        "event_count": len(envelopes),
        "state": state.get_state(),
    }
