"""Loopback-only form host for the independent intent overlay prototype.

Run: uv run python examples/intent-layer/form_backend.py
State is in memory and resets on restart. The demo reply is a fixed fixture,
not an AI provider. Host application and thread persistence are separate.
"""
from __future__ import annotations

import argparse
import math
import time
from copy import deepcopy
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from intent_layer.actor import Actor, actor_scope
from intent_layer.adapters.http import create_router
from intent_layer.errors import ThreadError
from intent_layer.memory_store import MemoryIntentStore
from intent_layer.ports import AppliedSuggestion, ThreadContext
from intent_layer.service import IntentService
from intent_layer.signals import MemoryPendingSignals


class FormHost:
    """Two typed fields with prevalidated batch application and exact undo."""

    def __init__(self) -> None:
        self.fields: dict[str, Any] = {"email": "old@example.test", "max_flow": 42.0}
        self.revision = 0

    def ensure_available(self, operation: str) -> None:
        return None

    def validate_targets(self, raw: Any) -> list[str]:
        raw = [] if raw is None else raw
        if not isinstance(raw, list) or any(
            not isinstance(field, str) or field not in self.fields for field in raw
        ):
            raise ThreadError("invalid_targets", "targets must name email or max_flow")
        return list(raw)

    def encode_targets(self, targets: list[Any]) -> list[str]:
        return self.validate_targets(targets)

    def decode_targets(self, raw: list[Any]) -> list[str]:
        return self.validate_targets(raw)

    def validate_ops(self, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list) or not raw:
            raise ThreadError("invalid_ops", "a non-empty FieldSet batch is required")
        for op in raw:
            if not isinstance(op, dict) or op.get("type") != "FieldSet":
                raise ThreadError("invalid_ops", "expected a FieldSet operation")
            payload = op.get("payload")
            if (not isinstance(payload, dict) or not isinstance(payload.get("field"), str)
                    or payload["field"] not in self.fields):
                raise ThreadError("invalid_ops", "FieldSet must name email or max_flow")
            field, value = payload["field"], payload.get("value")
            try:
                valid = isinstance(value, str) if field == "email" else (
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) and value >= 0
                )
            except OverflowError:
                valid = False
            if not valid:
                raise ThreadError("invalid_ops", "email needs text; max_flow needs a finite nonnegative number")
        return deepcopy(raw)

    async def base_version(self, origin_id: str) -> int:
        if origin_id != "signup":
            raise ThreadError("invalid_targets", "the form origin is signup")
        return self.revision

    async def apply(self, context: ThreadContext, ops: list[dict[str, Any]]) -> AppliedSuggestion:
        clean = self.validate_ops(ops)
        if context.origin_id != "signup" or any(
            op["payload"]["field"] not in context.targets for op in clean
        ):
            raise ThreadError("invalid_ops", "FieldSet must stay within the selected signup fields")
        shadow, undo = dict(self.fields), []
        for op in clean:
            field, value = op["payload"]["field"], op["payload"]["value"]
            undo.insert(0, {"type": "FieldSet", "payload": {"field": field, "value": shadow[field]}})
            shadow[field] = value
        self.fields = shadow
        self.revision += 1
        return AppliedSuggestion(undo, [self.revision], {"form": "signup", "revision": self.revision})

    async def revert(self, context: ThreadContext, undo: list[dict[str, Any]]) -> dict[str, Any]:
        return (await self.apply(context, undo)).result


def create_app() -> FastAPI:
    host, signals = FormHost(), MemoryPendingSignals()
    service = IntentService(MemoryIntentStore(), signals, host=host, now=time.time)
    app = FastAPI(title="Independent intent-layer form example")
    app.state.form_host = host
    app.state.intent_service = service
    app.include_router(create_router(lambda: service, lambda: signals, prefix="/form/inbox"))

    @app.get("/form/state")
    async def state():
        return {"fields": dict(host.fields), "revision": host.revision}

    @app.post("/form/demo-reply/{intent_id}")
    async def demo_reply(intent_id: str):
        intent = await service.get(intent_id)
        if intent is None:
            return JSONResponse(status_code=404, content={"error": "not_found", "id": intent_id})
        values = {"email": "work@example.test", "max_flow": 99.0}
        try:
            if intent.origin_canvas_id != "signup":
                raise ThreadError("invalid_targets", "the form origin is signup")
            ops = [{"type": "FieldSet", "payload": {"field": field, "value": values[field]}}
                   for field in host.decode_targets(intent.targets)]
            if not ops:
                raise ThreadError("invalid_targets", "select at least one form field")
            with actor_scope(Actor(kind="agent", id="form-demo", label="Fixed demo fixture")):
                await service.add_item(intent_id, type="question", text="Apply these demo values?",
                                       options=["Yes", "No"])
                updated, item = await service.add_item(intent_id, type="suggestion", ops=ops,
                                                       text="Fixed demo FieldSet proposal")
            return {"intent": updated.to_dict(), "item": item.to_dict()}
        except ThreadError as exc:
            return JSONResponse(status_code=400, content={"error": exc.code, "message": exc.message})

    return app


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port)
