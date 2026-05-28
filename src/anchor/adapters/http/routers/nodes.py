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
    # `model_dump(exclude_unset=True)` lets us distinguish "parent omitted"
    # from "parent explicitly set to null" — the latter is how the
    # frontend unparents a node (drop outside any Area). `exclude_none` is
    # WRONG for parent because null IS a meaningful value.
    raw = req.model_dump(exclude_unset=True)
    # Defensive: a node can't be its own parent.
    if raw.get("parent") == node_id:
        raise HTTPException(400, "node cannot be its own parent")
    try:
        # Pure-move heuristic — preserved for event-type clarity.
        if {"x", "y"} <= raw.keys() and len(raw) == 2 and raw.get("x") is not None and raw.get("y") is not None:
            state, env = await svc.move_node(slug, node_id, raw["x"], raw["y"])
        # Pure-reparent: a patch containing only `parent` dispatches the
        # dedicated `reparent_node` command so the canonical event is
        # `NodeReparented` (not a generic NodeUpdated). Adapters and SSE
        # consumers can then act on the precise intent.
        elif set(raw.keys()) == {"parent"}:
            state, env = await svc.reparent_node(slug, node_id, raw["parent"])
        else:
            # Mixed patch — strip `parent` out so the generic update doesn't
            # silently bypass the reparent invariant checks, then dispatch a
            # separate reparent if needed afterwards.
            if "parent" in raw:
                parent_val = raw.pop("parent")
                fields = {k: v for k, v in raw.items() if v is not None}
                if fields:
                    await svc.update_node(slug, node_id, fields)
                state, env = await svc.reparent_node(slug, node_id, parent_val)
            else:
                fields = {k: v for k, v in raw.items() if v is not None}
                if not fields:
                    raise HTTPException(400, "nothing to update")
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
