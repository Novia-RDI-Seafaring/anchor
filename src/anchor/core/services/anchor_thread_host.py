"""Anchor's thread host: legacy canvas targets, commands and inverse batches."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import JsonValue

from anchor.core.intents.errors import SuggestionApplyError, ThreadError
from anchor.core.intents.intent import SUGGESTION_OP_TYPES
from anchor.core.ports.thread_host import AppliedSuggestion, ThreadContext
from anchor.core.services.workspace_batch import BatchApplyError
from anchor.core.services.workspace_service import WorkspaceService


def _validate_targets(targets: Any) -> list[dict[str, Any]]:
    if targets is None:
        return []
    if not isinstance(targets, list):
        raise ThreadError("invalid_targets", "targets must be a list of {workspace_id, node_id}")
    out: list[dict[str, Any]] = []
    for t in targets:
        if not isinstance(t, dict):
            raise ThreadError("invalid_targets", "each target must be {workspace_id, node_id}")
        ws = t.get("workspace_id")
        node = t.get("node_id")
        if not isinstance(ws, str) or not ws or not isinstance(node, str) or not node:
            raise ThreadError(
                "invalid_targets", "each target needs string workspace_id and node_id",
            )
        out.append({"workspace_id": ws, "node_id": node})
    return out


def _inverse_data(patch: Any, was: Any) -> Any:
    """The data patch that undoes ``patch`` on data that was ``was``.

    Node data is deep-merged, so writing the old dict back would leave any
    key the change added in place. Every key the patch touched goes back to
    its old value, and a key that did not exist before is deleted (``None``
    is the merge's delete). Nested dicts are undone the same way.
    """
    if not isinstance(patch, dict) or not isinstance(was, dict):
        return was
    out: dict[str, Any] = {}
    for key, value in patch.items():
        if key not in was:
            out[key] = None
        elif isinstance(value, dict) and isinstance(was[key], dict):
            out[key] = _inverse_data(value, was[key])
        else:
            out[key] = was[key]
    return out


def _undo_for(
    before: dict[str, Any],
    ops: list[dict[str, Any]],
    id_map: dict[str, str],
) -> list[dict[str, Any]]:
    """The ops that put a canvas back to ``before`` after ``ops`` ran.

    Each op's inverse, in reverse order. An add becomes a remove of the id it
    was actually given; an update restores the fields it touched from the
    node as it was; a removal re-adds the node as it was together with the
    edges that cascaded away with it. Anything that cannot be inverted --
    an update to a node that did not exist -- is simply not in the list, as
    the batch would have refused it anyway.
    """
    nodes = {n["id"]: n for n in before.get("nodes", []) if isinstance(n, dict)}
    edges = {e["id"]: e for e in before.get("edges", []) if isinstance(e, dict)}
    real = lambda given: id_map.get(given, given)  # noqa: E731

    def edge_payload(e: dict[str, Any]) -> dict[str, Any]:
        # Handles under both spellings: the command model reads the alias.
        out = dict(e)
        if "sourceHandle" in out:
            out["source_handle"] = out["sourceHandle"]
        if "targetHandle" in out:
            out["target_handle"] = out["targetHandle"]
        return out

    undo: list[dict[str, Any]] = []
    for op in reversed(ops):
        kind = op.get("type")
        payload = op.get("payload") or {}
        ident = str(payload.get("id") or "")
        if kind == "NodeAdded":
            undo.append({"type": "NodeRemoved", "payload": {"id": real(ident)}})
        elif kind == "NodeUpdated":
            was = nodes.get(ident)
            if was is None:
                continue
            fields = payload.get("fields") or {}
            undo.append({
                "type": "NodeUpdated",
                "payload": {"id": ident, "fields": {
                    k: _inverse_data(fields[k], was.get(k)) if k == "data" else was.get(k)
                    for k in fields
                }},
            })
        elif kind == "NodeRemoved":
            was = nodes.get(ident)
            if was is None:
                continue
            undo.append({"type": "NodeAdded", "payload": dict(was)})
            for e in edges.values():
                if e.get("source") == ident or e.get("target") == ident:
                    undo.append({"type": "EdgeAdded", "payload": edge_payload(e)})
        elif kind == "EdgeAdded":
            undo.append({"type": "EdgeRemoved", "payload": {"id": real(ident)}})
        elif kind == "EdgeRemoved":
            was = edges.get(ident)
            if was is not None:
                undo.append({"type": "EdgeAdded", "payload": edge_payload(was)})
        elif kind == "EdgeUpdated":
            was = edges.get(ident)
            if was is None:
                continue
            fields = payload.get("fields") or {}
            undo.append({
                "type": "EdgeUpdated",
                "payload": {"id": ident, "fields": {k: was.get(k) for k in fields}},
            })
    return undo


def _validate_ops(ops: Any) -> list[dict[str, Any]]:
    """Shape-check a suggestion's ops at post time. Canvas-level validity
    (does the node exist, is the payload complete) is checked at apply
    time against the live state, so a suggestion can be staged against a
    canvas that keeps moving."""
    if not isinstance(ops, list) or not ops:
        raise ThreadError("invalid_ops", "a suggestion needs a non-empty ops list")
    out: list[dict[str, Any]] = []
    for index, op in enumerate(ops):
        if not isinstance(op, dict):
            raise ThreadError("invalid_ops", f"op {index} must be an object {{type, payload}}")
        op_type = op.get("type")
        if op_type not in SUGGESTION_OP_TYPES:
            raise ThreadError(
                "invalid_ops",
                f"op {index}: unknown type {op_type!r}; expected one of "
                f"{', '.join(SUGGESTION_OP_TYPES)}",
            )
        payload = op.get("payload")
        if not isinstance(payload, dict):
            raise ThreadError("invalid_ops", f"op {index}: payload must be an object")
        out.append({"type": op_type, "payload": dict(payload)})
    return out


class AnchorThreadHost:
    """Compatibility host, including validation when no workspace is wired."""

    def __init__(self, workspace: WorkspaceService | None) -> None:
        self._workspace = workspace

    def ensure_available(self, operation: str) -> None:
        if self._workspace is None:
            raise ThreadError(
                "workspace_unavailable", f"no workspace service is wired for {operation}",
            )

    def validate_targets(self, raw: Any) -> list[JsonValue]:
        return list(_validate_targets(raw))

    def encode_targets(self, targets: list[JsonValue]) -> list[JsonValue]:
        return deepcopy(targets)

    def decode_targets(self, raw: list[JsonValue]) -> list[JsonValue]:
        return deepcopy(raw)

    def validate_ops(self, raw: Any) -> list[dict[str, Any]]:
        return _validate_ops(raw)

    async def base_version(self, origin_id: str) -> int | None:
        return await self._workspace.version_of(origin_id) if self._workspace is not None else None

    @staticmethod
    def _canvas(context: ThreadContext) -> str:
        if context.origin_id:
            return context.origin_id
        for target in context.targets:
            if not isinstance(target, dict):
                continue
            ws = target.get("workspace_id")
            if isinstance(ws, str) and ws:
                return ws
        raise ThreadError("no_canvas", f"intent {context.intent_id!r} names no canvas to apply to")

    async def apply(self, context: ThreadContext, ops: list[dict[str, Any]]) -> AppliedSuggestion:
        self.ensure_available("apply")
        assert self._workspace is not None
        slug = self._canvas(context)
        # Snapshot and batch application remain separate, as before this seam.
        before = await self._workspace.get_state(slug)
        try:
            _state, envelopes, id_map = await self._workspace.apply_batch(
                slug, ops, actor=context.author, causation_id=context.item_id,
                approver=context.approver,
            )
        except BatchApplyError as exc:
            raise SuggestionApplyError(exc) from exc
        versions = [env.version for env in envelopes]
        return AppliedSuggestion(
            undo=_undo_for(before, ops, dict(id_map)),
            versions=versions,
            result={
                "workspace_id": slug,
                "versions": versions,
                "id_map": dict(id_map),
                "events": [env.model_dump() for env in envelopes],
            },
        )

    async def revert(self, context: ThreadContext, undo: list[dict[str, Any]]) -> dict[str, Any]:
        self.ensure_available("revert")
        assert self._workspace is not None
        slug = self._canvas(context)
        try:
            _state, envelopes, _ids = await self._workspace.apply_batch(
                slug, undo, actor=context.approver, causation_id=context.item_id,
                approver=context.approver, restore=True,
            )
        except BatchApplyError as exc:
            raise SuggestionApplyError(exc) from exc
        return {
            "workspace_id": slug,
            "versions": [env.version for env in envelopes],
            "events": [env.model_dump() for env in envelopes],
        }
