"""The public thread service works with a form, without any canvas runtime."""
from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

import pytest
from pydantic import JsonValue

from anchor.core.events.actor import Actor, actor_scope
from anchor.core.intents.errors import SuggestionApplyError, ThreadError
from anchor.core.intents.intent import Intent
from anchor.core.ports.thread_host import AppliedSuggestion, ThreadContext
from anchor.core.services.intent_service import IntentService, UnknownIntentKindError
from anchor.infra.stores.fs_intent_store import FsIntentStore
from anchor.infra.stores.memory_intent_store import MemoryIntentStore

AUTHOR = Actor(kind="agent", label="form helper")
APPROVER = Actor(kind="human", label="form reader")


class RecordingBus:
    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)


class FormRejected(ThreadError):
    def __init__(self, index: int, reason: str, *, stale: bool = False):
        super().__init__("invalid_ops", reason)
        self.failing_index = index
        self.reason = reason
        self.stale = stale


class FormHost:
    """Own field IDs, values, revisions and inverses. No nodes or workspace."""

    def __init__(self):
        self.fields = {"email": "old@example.test", "max_flow": 42.0}
        self.revision = 0
        self.available = True
        self.applications: list[ThreadContext] = []

    def ensure_available(self, operation: str) -> None:
        if not self.available:
            raise ThreadError("form_unavailable", f"form is unavailable for {operation}")

    def validate_targets(self, raw: Any) -> list[JsonValue]:
        if raw is None:
            return []
        if not isinstance(raw, list) or any(
            not isinstance(field, str) or field not in self.fields for field in raw
        ):
            raise ThreadError("invalid_targets", "form targets must name existing fields")
        return list(raw)

    def encode_targets(self, targets: list[JsonValue]) -> list[JsonValue]:
        return list(targets)

    def decode_targets(self, raw: list[JsonValue]) -> list[JsonValue]:
        return self.validate_targets(raw)

    def validate_ops(self, raw: Any) -> list[dict[str, Any]]:
        if not isinstance(raw, list) or not raw:
            raise ThreadError("invalid_ops", "a form suggestion needs field changes")
        for index, op in enumerate(raw):
            if not isinstance(op, dict) or op.get("type") != "FieldSet":
                raise FormRejected(index, "expected FieldSet")
            payload = op.get("payload")
            if not isinstance(payload, dict) or payload.get("field") not in self.fields:
                raise FormRejected(index, "unknown form field", stale=True)
            value = payload.get("value")
            if payload["field"] == "email" and not isinstance(value, str):
                raise FormRejected(index, "email needs text")
            if payload["field"] == "max_flow" and (
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0
            ):
                raise FormRejected(index, "max_flow needs a finite nonnegative number")
        return deepcopy(raw)

    async def base_version(self, origin_id: str) -> int | None:
        return self.revision if origin_id == "registration-form" else None

    async def apply(self, context: ThreadContext, ops: list[dict[str, Any]]) -> AppliedSuggestion:
        self.ensure_available("apply")
        try:
            clean = self.validate_ops(ops)
        except FormRejected as exc:
            raise SuggestionApplyError(exc) from exc
        shadow = dict(self.fields)
        undo = []
        for op in clean:
            field = op["payload"]["field"]
            undo.insert(0, {"type": "FieldSet", "payload": {"field": field, "value": shadow[field]}})
            shadow[field] = op["payload"]["value"]
        self.fields = shadow
        self.revision += 1
        self.applications.append(context)
        return AppliedSuggestion(undo, [self.revision], {
            "form": "registration-form", "revision": self.revision,
        })

    async def revert(self, context: ThreadContext, undo: list[dict[str, Any]]) -> dict[str, Any]:
        # The host owns attribution for a reverse application too.
        reverse = ThreadContext(context.intent_id, context.origin_id, context.targets,
                                context.item_id, context.approver, context.approver)
        applied = await self.apply(reverse, undo)
        return {**applied.result, "versions": applied.versions}


def field_set(field, value):
    return {"type": "FieldSet", "payload": {"field": field, "value": value}}


async def form_thread(service, *, targets=None):
    return await service.enqueue("user_request", origin_canvas_id="registration-form",
                                 targets=targets if targets is not None else ["email"],
                                 payload={"text": "Please check the form"})


@pytest.mark.asyncio
async def test_field_targets_thread_lifecycle_and_count_only_signal():
    host, bus = FormHost(), RecordingBus()
    service = IntentService(MemoryIntentStore(), bus, host=host, now=lambda: 10.0)
    requested = ["email", "max_flow"]
    intent = await form_thread(service, targets=requested)
    requested.clear()
    assert intent.targets == ["email", "max_flow"]
    assert intent.base_version == 0
    assert Intent.from_dict(intent.to_dict()).targets == intent.targets
    with actor_scope(AUTHOR):
        _, question = await service.add_item(intent.id, type="question", text="Which address?",
                                            options=["Work", "Home"])
        _, note = await service.add_item(intent.id, type="message", text="Checking values",
                                        place={"x": 4, "y": 6})
    with actor_scope(APPROVER):
        _, answered = await service.answer_question(intent.id, question.id, text="Work")
    assert answered.answer == "Work" and answered.state == "answered"
    _, updated = await service.update_item(intent.id, note.id, state="done")
    assert updated.state == "done" and updated.author == AUTHOR
    await service.resolve(intent.id, {"checked": True})
    assert [event.payload for event in bus.events] == [{"count": 1}] * 5 + [{"count": 0}]
    assert all(event.workspace_id == "registration-form" for event in bus.events)
    assert all(event.type == "IntentPending" for event in bus.events)


@pytest.mark.asyncio
async def test_persisted_field_apply_revert_after_service_and_store_restart(tmp_path):
    host, bus = FormHost(), RecordingBus()
    service = IntentService(FsIntentStore(tmp_path), bus, host=host)
    intent = await form_thread(service)
    with actor_scope(AUTHOR):
        _, item = await service.add_item(intent.id, type="suggestion", ops=[
            field_set("email", "first@example.test"), field_set("email", "final@example.test"),
            field_set("max_flow", 99.0),
        ])
    with actor_scope(APPROVER):
        applied, item, result = await service.apply_suggestion(intent.id, item.id)
    assert result == {"form": "registration-form", "revision": 1}
    assert host.fields == {"email": "final@example.test", "max_flow": 99.0}
    assert item.state == "applied" and item.applied_versions == [1]
    assert host.applications[0].author == AUTHOR
    assert host.applications[0].approver == APPROVER
    assert host.applications[0].item_id == item.id
    assert host.applications[0].targets == ["email"]
    restarted = IntentService(FsIntentStore(tmp_path), bus, host=host)
    restored = await restarted.get(intent.id)
    assert restored.targets == ["email"]
    assert restored.items[0].undo_ops == applied.items[0].undo_ops
    with actor_scope(APPROVER):
        _, reverted, result = await restarted.revert_suggestion(intent.id, item.id)
    assert result == {"form": "registration-form", "revision": 2, "versions": [2]}
    assert host.fields == {"email": "old@example.test", "max_flow": 42.0}
    assert reverted.state == "reverted"
    assert host.applications[-1].author == host.applications[-1].approver == APPROVER
    assert host.applications[-1].item_id == item.id


@pytest.mark.asyncio
async def test_host_rejection_is_atomic_and_retains_pending_thread():
    host, store, bus = FormHost(), MemoryIntentStore(), RecordingBus()
    service = IntentService(store, bus, host=host)
    intent = await form_thread(service)
    _, item = await service.add_item(intent.id, type="suggestion", ops=[
        field_set("email", "new@example.test"), field_set("max_flow", 99),
    ])
    del host.fields["max_flow"]  # Host state changed after staging.
    before = dict(host.fields)
    with pytest.raises(SuggestionApplyError) as failure:
        await service.apply_suggestion(intent.id, item.id)
    assert failure.value.to_dict() == {
        "error": "apply_failed", "failing_index": 1, "failing_op_index": 1,
        "reason": "unknown form field", "stale": True,
    }
    assert host.fields == before and host.revision == 0 and host.applications == []
    assert (await service.get(intent.id)).items[0].state == "pending"
    assert len(bus.events) == 2


@pytest.mark.asyncio
async def test_decline_supersede_resolve_and_legacy_undo():
    host, bus = FormHost(), RecordingBus()
    service = IntentService(MemoryIntentStore(), bus, host=host)
    intent = await form_thread(service)
    _, first = await service.add_item(intent.id, type="suggestion", ops=[field_set("max_flow", 10)])
    _, second = await service.add_item(intent.id, type="suggestion", supersedes=first.id,
                                       ops=[field_set("max_flow", 20)])
    assert (await service.get(intent.id)).items[0].state == "superseded"
    await service.decline_suggestion(intent.id, second.id)
    assert host.revision == 0
    _, final = await service.add_item(intent.id, type="suggestion", ops=[field_set("max_flow", 30)])
    await service.resolve(intent.id)
    await service.apply_suggestion(intent.id, final.id)  # Resolved threads retain pending suggestions.
    assert host.fields["max_flow"] == 30
    legacy = await service.get(intent.id)
    legacy.find_item(final.id).undo_ops = None
    await service._store.replace(legacy)
    with pytest.raises(ThreadError, match="without a way back") as failure:
        await service.revert_suggestion(intent.id, final.id)
    assert failure.value.code == "no_undo" and host.revision == 1


@pytest.mark.asyncio
async def test_default_host_validation_and_availability_precedence():
    bus = RecordingBus()
    service = IntentService(MemoryIntentStore(), bus)
    with pytest.raises(UnknownIntentKindError):
        await service.enqueue("unknown", targets=["email"])
    with pytest.raises(ThreadError) as failure:
        await service.enqueue("user_request", targets=["email"])
    assert failure.value.code == "invalid_targets"
    assert failure.value.message == "each target must be {workspace_id, node_id}"
    for operation in ("apply", "revert"):
        with pytest.raises(ThreadError) as failure:
            await getattr(service, f"{operation}_suggestion")("missing-intent", "missing-item")
        assert failure.value.code == "workspace_unavailable"
        assert failure.value.message == f"no workspace service is wired for {operation}"
    host = FormHost()
    host.available = False
    service = IntentService(MemoryIntentStore(), bus, host=host)
    with pytest.raises(ThreadError) as failure:
        await service.apply_suggestion("missing-intent", "missing-item")
    assert failure.value.code == "form_unavailable"
    assert bus.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
async def test_form_validation_rejects_bad_numeric_field_before_staging(value):
    host = FormHost()
    service = IntentService(MemoryIntentStore(), RecordingBus(), host=host)
    intent = await form_thread(service)
    with pytest.raises(ThreadError):
        await service.add_item(intent.id, type="suggestion", ops=[field_set("max_flow", value)])
    assert (await service.get(intent.id)).items == [] and host.revision == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), {1: "bad key"}, {"not-json"}])
async def test_target_codec_cannot_persist_non_json_values(bad):
    class BadCodec(FormHost):
        def encode_targets(self, targets):
            return [{"metadata": bad}]

    bus = RecordingBus()
    service = IntentService(MemoryIntentStore(), bus, host=BadCodec())
    with pytest.raises(ThreadError) as failure:
        await form_thread(service)
    assert failure.value.code == "invalid_targets"
    assert await service.list_all() == [] and bus.events == []


@pytest.mark.asyncio
async def test_host_receives_detached_targets_ops_and_undo():
    class EditingHost(FormHost):
        async def apply(self, context, ops):
            applied = await super().apply(context, ops)
            context.targets.append("max_flow")
            ops[0]["payload"]["value"] = "host changed its input"
            return applied

        async def revert(self, context, undo):
            result = await super().revert(context, undo)
            undo[0]["payload"]["value"] = "host changed its inverse input"
            return result

    host = EditingHost()
    service = IntentService(MemoryIntentStore(), RecordingBus(), host=host)
    intent = await form_thread(service)
    _, item = await service.add_item(intent.id, type="suggestion",
                                     ops=[field_set("email", "new@example.test")])
    applied, _, _ = await service.apply_suggestion(intent.id, item.id)
    assert applied.targets == ["email"]
    assert applied.items[0].ops == [field_set("email", "new@example.test")]
    original_undo = deepcopy(applied.items[0].undo_ops)
    reverted, _, _ = await service.revert_suggestion(intent.id, item.id)
    assert reverted.items[0].undo_ops == original_undo
    assert reverted.targets == ["email"]


def test_legacy_target_metadata_and_undo_round_trip_without_normalizing():
    raw = {
        "id": "legacy", "kind": "user_request",
        "targets": [{"workspace_id": "cv", "node_id": "n1", "metadata": {"rank": 1, "tags": ["old"]}}],
        "items": [{"id": "suggestion", "type": "suggestion", "author": {"kind": "agent"},
                   "state": "applied", "undo_ops": [field_set("email", "old@example.test")]}],
    }
    restored = Intent.from_dict(raw)
    encoded = restored.to_dict()
    assert encoded["targets"] == raw["targets"]
    assert encoded["items"][0]["undo_ops"] == raw["items"][0]["undo_ops"]
    encoded["targets"][0]["metadata"]["tags"].append("output changed")
    raw["targets"][0]["metadata"]["tags"].append("input changed")
    assert restored.targets[0]["metadata"]["tags"] == ["old"]
