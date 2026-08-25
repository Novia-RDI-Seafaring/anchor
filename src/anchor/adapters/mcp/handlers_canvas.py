"""MCP tool definitions backed by WorkspaceService.

Tool names keep the v1 `canvas_*` prefix so existing agent prompts continue
to work; every tool now takes `workspace_slug` as its first arg.
"""
from __future__ import annotations

import base64
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from anchor.adapters.mcp import canvas_tool_definitions
from anchor.core.services.workspace_service import WorkspaceService
from anchor.core.workspace.workspace import CommandError


def tool_definitions() -> list[dict[str, Any]]:
    """Return the canvas MCP catalog from its focused definition module."""
    return canvas_tool_definitions.tool_definitions()


# ── Byte-fetch envelope ─────────────────────────────────────────────────────
#
# Mirrors the contract used by anchor_pdfs.mcp_handlers._byte_envelope.
# Duplicated rather than imported because adapters/mcp/handlers_canvas
# is in core-adjacent code that shouldn't depend on an extension. The
# contract is *the* shared piece — keep these two implementations in sync.
def _byte_envelope_from_result(*, path: Path | None, bytes_: bytes | None, content_type: str, fmt: str) -> str:
    if fmt == "path":
        if path is None:
            return json.dumps({"error": "snapshot returned inline bytes; request format='base64'"})
        return json.dumps({
            "format": "path", "value": str(path), "content_type": content_type,
            "size_bytes": path.stat().st_size if path.exists() else None,
        })
    if fmt == "base64":
        raw = bytes_ if bytes_ is not None else (path.read_bytes() if path else b"")
        return json.dumps({
            "format": "base64",
            "value": base64.b64encode(raw).decode("ascii"),
            "content_type": content_type,
            "size_bytes": len(raw),
        })
    if fmt == "inline":
        # Hand the raw bytes back via the special _mcp_image_b64 marker so
        # the MCP server wrapper can promote the result to an MCP
        # ImageContent block and have the host harness display it inline.
        # SVG is not an image content type in MCP today; emit it as text.
        raw = bytes_ if bytes_ is not None else (path.read_bytes() if path else b"")
        if content_type.startswith("image/") and content_type != "image/svg+xml":
            return json.dumps({
                "_mcp_image_b64": base64.b64encode(raw).decode("ascii"),
                "_mcp_mime": content_type,
            })
        return json.dumps({
            "format": "base64",
            "value": base64.b64encode(raw).decode("ascii"),
            "content_type": content_type,
            "size_bytes": len(raw),
        })
    return json.dumps({"error": f"unknown format: {fmt!r} (use 'path', 'base64', or 'inline')"})
# Non-fatal nudge for the #131 failure mode: an agent dumps tabular facts into
# a spec node's prose `description` instead of structured `data.rows`. Prose is
# still allowed (some specs really are a caption), so this never blocks the
# write -- it only attaches a `hint` to the tool result steering the next call
# toward rows. Returns None when no nudge applies.
_SPEC_ROWS_HINT = (
    "This `spec` node has a prose `description` but no `data.rows`. "
    "If it holds tabular facts (IDs, values, measurements), move them into "
    "`data.rows` as [{key, value, source_ref}] so they render as a clean, "
    "source-clickable table. Keep `description` only for a short caption."
)


def _alias_type(args: dict[str, Any], canonical: str) -> None:
    """Accept ``type`` as an alias for ``node_type`` / ``edge_type`` (#186).

    Canvas state JSON exposes ``node_type`` / ``edge_type``; the write
    surfaces historically diverged. We now accept BOTH on every write
    surface so an agent can read a record's ``node_type`` and write it
    straight back. ``node_type`` / ``edge_type`` is canonical and wins if
    both are present; a bare ``type`` is promoted to the canonical key."""
    if "type" in args:
        alias = args.pop("type")
        args.setdefault(canonical, alias)


def _data_warning(svc: WorkspaceService, node_type: str | None, data: dict[str, Any] | None) -> str | None:
    """Non-blocking warning listing data keys the node type won't render (#191)."""
    if not node_type:
        return None
    unknown = svc.unknown_data_keys(node_type, data)
    if not unknown:
        return None
    keys = ", ".join(unknown)
    return (
        f"node_type {node_type!r} does not render these data keys: {keys}. "
        f"They are stored but never shown. Call canvas_node_types to see "
        f"which data fields {node_type!r} renders (e.g. its body field)."
    )


def _spec_rows_hint(node_type: str | None, data: dict[str, Any] | None) -> str | None:
    if node_type != "spec":
        return None
    data = data or {}
    has_rows = bool(data.get("rows"))
    has_description = bool(str(data.get("description") or "").strip())
    if has_description and not has_rows:
        return _SPEC_ROWS_HINT
    return None


NodeFieldsEnricher = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def call_tool(
    svc: WorkspaceService,
    name: str,
    args: dict[str, Any],
    *,
    enrich_node_fields: NodeFieldsEnricher | None = None,
) -> str:
    try:
        if name == "canvas_get_state":
            return json.dumps(await svc.get_state(args["workspace_slug"]))
        if name == "canvas_create_workspace":
            return json.dumps(await svc.create_workspace(args["slug"], title=args.get("title", "")))
        if name == "canvas_delete_workspace":
            return json.dumps(await svc.delete_workspace(args["workspace_slug"]))
        if name == "canvas_list_workspaces":
            return json.dumps(await svc.list_workspaces())
        if name == "canvas_add_node":
            slug = args.pop("workspace_slug")
            _alias_type(args, "node_type")
            place = args.pop("place", None)
            hint = _spec_rows_hint(args.get("node_type"), args.get("data"))
            warning = _data_warning(svc, args.get("node_type"), args.get("data"))
            state, env = await svc.add_node(slug, place=place, **args)
            result: dict[str, Any] = {"event": env.model_dump(), "state": state.get_state()}
            # Echo the resolved position so the agent can track layout (#189).
            result["position"] = {"x": env.payload.get("x"), "y": env.payload.get("y")}
            if hint is not None:
                result["hint"] = hint
            if warning is not None:
                result["warning"] = warning
            return json.dumps(result)
        if name == "canvas_node_types":
            return json.dumps(svc.node_types_schema(args.get("node_type")))
        if name == "canvas_update_node":
            slug = args.pop("workspace_slug")
            node_id = args.pop("id")
            data_patch = args.get("data") if isinstance(args.get("data"), dict) else None
            # `parent` is allowed to be explicitly None (means "unparent");
            # only strip the OTHER fields if they're None. The dispatcher
            # mirrors the HTTP route so HTTP / MCP / CLI behave identically.
            parent_present = "parent" in args
            parent_val = args.pop("parent", None)
            if parent_present and parent_val == node_id:
                return json.dumps({"error": "node cannot be its own parent"})
            fields = {k: v for k, v in args.items() if v is not None}
            if {"x", "y"} <= fields.keys() and len(fields) == 2 and not parent_present:
                state, env = await svc.move_node(slug, node_id, fields["x"], fields["y"])
            elif parent_present and not fields:
                state, env = await svc.reparent_node(slug, node_id, parent_val)
            else:
                if parent_present:
                    if enrich_node_fields:
                        fields = await enrich_node_fields(fields)
                    await svc.update_node(slug, node_id, fields)
                    state, env = await svc.reparent_node(slug, node_id, parent_val)
                else:
                    if not fields:
                        return json.dumps({"error": "nothing to update"})
                    if enrich_node_fields:
                        fields = await enrich_node_fields(fields)
                    state, env = await svc.update_node(slug, node_id, fields)
            result = {"event": env.model_dump(), "state": state.get_state()}
            if data_patch is not None:
                node = state.nodes.get(node_id)
                warning = _data_warning(
                    svc, node.node_type if node else None, data_patch,
                )
                if warning is not None:
                    result["warning"] = warning
            return json.dumps(result)
        if name == "canvas_remove_node":
            state, envelopes = await svc.remove_node(args["workspace_slug"], args["id"])
            return json.dumps({"events": [e.model_dump() for e in envelopes], "state": state.get_state()})
        if name == "canvas_add_edge":
            slug = args.pop("workspace_slug")
            _alias_type(args, "edge_type")
            state, env = await svc.add_edge(slug, **args)
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_remove_edge":
            state, env = await svc.remove_edge(args["workspace_slug"], args["id"])
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_update_edge":
            slug = args.pop("workspace_slug")
            edge_id = args.pop("id")
            _alias_type(args, "edge_type")
            fields = {k: v for k, v in args.items() if v is not None}
            state, env = await svc.update_edge(slug, edge_id, fields)
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_clear":
            state, env = await svc.clear(args["workspace_slug"])
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_organize_subtree":
            try:
                state, envelopes = await svc.organize_subtree(
                    args["workspace_slug"], args["root_id"],
                    orientation=args.get("orientation", "vertical"),
                    algo=args.get("algo", "dagre"),
                    direction=args.get("direction", "any"),
                )
            except ValueError as e:
                return json.dumps({"error": str(e)})
            moves = [
                {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
                for env in envelopes
            ]
            return json.dumps({
                "moves": moves,
                "event_count": len(envelopes),
                "state": state.get_state(),
            })
        if name == "canvas_align":
            try:
                state, envelopes = await svc.align_nodes(
                    args["workspace_slug"], list(args["ids"]), args["anchor"],
                )
            except ValueError as e:
                return json.dumps({"error": str(e)})
            moves = [
                {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
                for env in envelopes
            ]
            return json.dumps({
                "moves": moves,
                "event_count": len(envelopes),
                "state": state.get_state(),
            })
        if name == "canvas_distribute":
            try:
                state, envelopes = await svc.distribute_nodes(
                    args["workspace_slug"], list(args["ids"]), args["axis"],
                )
            except ValueError as e:
                return json.dumps({"error": str(e)})
            moves = [
                {"id": env.payload["id"], "x": env.payload["x"], "y": env.payload["y"]}
                for env in envelopes
            ]
            return json.dumps({
                "moves": moves,
                "event_count": len(envelopes),
                "state": state.get_state(),
            })
        if name == "canvas_create_sub_canvas":
            return json.dumps(await svc.create_sub_canvas(
                args["parent_slug"], args["slug"],
                title=args.get("title", ""),
                x=float(args.get("x", 0.0)),
                y=float(args.get("y", 0.0)),
            ))
        if name == "canvas_list_placeholders":
            return json.dumps(await svc.list_placeholders(args["workspace_slug"]))
        if name == "canvas_create_reference":
            ref = await svc.create_reference(
                args["workspace_slug"],
                source_ref=args["source_ref"],
                label=args.get("label"),
                created_by=args.get("created_by", "agent"),
            )
            return json.dumps({"reference": ref})
        if name == "canvas_list_references":
            return json.dumps(await svc.list_references(args["workspace_slug"]))
        if name == "canvas_remove_reference":
            state, env = await svc.remove_reference(
                args["workspace_slug"], args["reference_id"],
            )
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_update_reference":
            state, env = await svc.update_reference(
                args["workspace_slug"],
                args["reference_id"],
                label=args.get("label"),
            )
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_attach_reference":
            state, env = await svc.attach_reference(
                args["workspace_slug"],
                args["reference_id"],
                node_id=args["node_id"],
                row_index=args.get("row_index"),
            )
            return json.dumps({"event": env.model_dump(), "state": state.get_state()})
        if name == "canvas_snapshot":
            envelope_fmt = args.get("format", "path")
            image_fmt = args.get("image_format", "png")
            viewport = args.get("viewport")
            if viewport is not None:
                viewport = (int(viewport[0]), int(viewport[1]))
            full_page = bool(args.get("full_page", True))
            try:
                result = await svc.snapshot(
                    args["workspace_slug"],
                    format=image_fmt,
                    viewport=viewport,
                    full_page=full_page,
                )
            except NotImplementedError as e:
                return json.dumps({"error": str(e)})
            except RuntimeError as e:
                return json.dumps({"error": str(e)})
            except ValueError as e:
                return json.dumps({"error": str(e)})
            return _byte_envelope_from_result(
                path=result.path, bytes_=result.bytes_,
                content_type=result.content_type, fmt=envelope_fmt,
            )
    except CommandError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"unknown tool: {name}"})
