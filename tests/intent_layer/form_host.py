"""A field host with no Anchor dependency or canvas command vocabulary."""
from copy import deepcopy

from intent_layer.errors import ThreadError
from intent_layer.ports import AppliedSuggestion


class FormHost:
    def __init__(self):
        self.fields = {"email": "old@example.test"}
        self.revision = 0
        self.contexts = []

    def ensure_available(self, operation):
        pass

    def validate_targets(self, raw):
        raw = [] if raw is None else raw
        if not isinstance(raw, list) or any(field not in self.fields for field in raw):
            raise ThreadError("invalid_targets", "target must name a form field")
        return list(raw)

    def encode_targets(self, targets):
        return list(targets)

    def decode_targets(self, targets):
        return self.validate_targets(targets)

    def validate_ops(self, raw):
        if not isinstance(raw, list) or not raw:
            raise ThreadError("invalid_ops", "a form change is required")
        for op in raw:
            if op.get("type") != "FieldSet" or op.get("payload", {}).get("field") not in self.fields:
                raise ThreadError("invalid_ops", "expected FieldSet for an existing field")
        return deepcopy(raw)

    async def base_version(self, origin):
        return self.revision

    async def apply(self, context, ops):
        clean = self.validate_ops(ops)
        shadow, undo = dict(self.fields), []
        for op in clean:
            field, value = op["payload"]["field"], op["payload"]["value"]
            undo.insert(0, {"type": "FieldSet", "payload": {"field": field, "value": shadow[field]}})
            shadow[field] = value
        self.fields = shadow
        self.revision += 1
        self.contexts.append(context)
        return AppliedSuggestion(undo, [self.revision], {"form": "signup", "revision": self.revision})

    async def revert(self, context, undo):
        applied = await self.apply(context, undo)
        return applied.result
