"""Node CRUD on a workspace."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from anchor.adapters.http.deps import get_doc_store, get_workspace_service
from anchor.adapters.http.schemas import AddNodeRequest, UpdateNodeRequest
from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.workspace.workspace import CommandError
from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.value_provenance import enrich_spec_row_source_refs

router = APIRouter(prefix="/api/workspaces", tags=["nodes"])
node_types_router = APIRouter(prefix="/api/node-types", tags=["nodes"])


def _data_warning(svc: WorkspaceService, node_type: str | None, data: dict | None) -> str | None:
    """List data keys ``node_type``'s renderer ignores, as a soft warning (#191)."""
    if not node_type:
        return None
    unknown = svc.unknown_data_keys(node_type, data)
    if not unknown:
        return None
    return (
        f"node_type {node_type!r} does not render these data keys: "
        f"{', '.join(unknown)}. They are stored but never shown. "
        f"GET /api/node-types/{node_type} for the renderable fields."
    )


@node_types_router.get("")
async def list_node_types(svc: WorkspaceService = Depends(get_workspace_service)):
    """Per-node-type data-field contract (#191). Same envelope as the
    ``canvas_node_types`` MCP tool and ``anchor canvas node-types`` CLI."""
    return svc.node_types_schema()


@node_types_router.get("/{node_type}")
async def get_node_type(node_type: str, svc: WorkspaceService = Depends(get_workspace_service)):
    schema = svc.node_types_schema(node_type)
    if not schema:
        raise HTTPException(404, f"unknown node_type {node_type!r}")
    return schema[0]


@router.post("/{slug}/nodes", status_code=201)
async def add_node(slug: str, req: AddNodeRequest, svc: WorkspaceService = Depends(get_workspace_service)):
    # `exclude_none` drops omitted x/y so the service auto-places (#189) and
    # drops the unused `type`/`node_type` alias. We resolve the alias and the
    # node_type default ourselves so both shapes are accepted (#186).
    kwargs = req.model_dump(exclude_none=True)
    place = kwargs.pop("place", None)
    node_type = kwargs.pop("node_type", None) or kwargs.pop("type", None) or "concept"
    kwargs.pop("type", None)
    kwargs["node_type"] = node_type
    try:
        state, env = await svc.add_node(slug, place=place, **kwargs)
    except CommandError as e:
        raise HTTPException(400, str(e))
    resp = {
        "event": env.model_dump(),
        "state": state.get_state(),
        # Echo the resolved position so the client can track layout (#189).
        "position": {"x": env.payload.get("x"), "y": env.payload.get("y")},
    }
    warning = _data_warning(svc, node_type, kwargs.get("data"))
    if warning is not None:
        resp["warning"] = warning
    return resp


@router.patch("/{slug}/nodes/{node_id}")
async def update_node(
    slug: str,
    node_id: str,
    req: UpdateNodeRequest,
    svc: WorkspaceService = Depends(get_workspace_service),
    doc_store: DocStore = Depends(get_doc_store),
):
    # `model_dump(exclude_unset=True)` lets us distinguish "parent omitted"
    # from "parent explicitly set to null" — the latter is how the
    # frontend unparents a node (drop outside any Area). `exclude_none` is
    # WRONG for parent because null IS a meaningful value.
    raw = req.model_dump(exclude_unset=True)
    data_patch = raw.get("data") if isinstance(raw.get("data"), dict) else None
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
                if "data" in fields:
                    fields["data"] = await enrich_spec_row_source_refs(fields["data"], doc_store)
                if fields:
                    await svc.update_node(slug, node_id, fields)
                state, env = await svc.reparent_node(slug, node_id, parent_val)
            else:
                fields = {k: v for k, v in raw.items() if v is not None}
                if not fields:
                    raise HTTPException(400, "nothing to update")
                if "data" in fields:
                    fields["data"] = await enrich_spec_row_source_refs(fields["data"], doc_store)
                state, env = await svc.update_node(slug, node_id, fields)
    except CommandError as e:
        raise HTTPException(400, str(e))
    resp = {"event": env.model_dump(), "state": state.get_state()}
    if data_patch is not None:
        node = state.nodes.get(node_id)
        warning = _data_warning(svc, node.node_type if node else None, data_patch)
        if warning is not None:
            resp["warning"] = warning
    return resp


@router.delete("/{slug}/nodes/{node_id}")
async def remove_node(slug: str, node_id: str, svc: WorkspaceService = Depends(get_workspace_service)):
    try:
        state, envelopes = await svc.remove_node(slug, node_id)
    except CommandError as e:
        raise HTTPException(400, str(e))
    return {"events": [e.model_dump() for e in envelopes], "state": state.get_state()}
