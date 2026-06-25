"""FsIntentStore: durable, rebuilt-from-disk project-level intent queue (#148)."""
from __future__ import annotations

from anchor.core.intents.intent import PENDING, RESOLVED, Intent
from anchor.infra.stores.fs_intent_store import FsIntentStore


async def test_add_get_list_round_trip(tmp_path):
    store = FsIntentStore(tmp_path)
    intent = Intent(
        kind="drop_to_ingest",
        origin_canvas_id="canvas-a",
        payload={"slug": "pump"},
        created_at=1.0,
    )
    await store.add(intent)

    got = await store.get(intent.id)
    assert got is not None
    assert got.kind == "drop_to_ingest"
    assert got.payload == {"slug": "pump"}
    assert [i.id for i in await store.list()] == [intent.id]


async def test_survives_a_fresh_store_instance(tmp_path):
    """A second store over the same dir rebuilds the queue from disk -- the
    durability property a restart / second process relies on."""
    await FsIntentStore(tmp_path).add(
        Intent(id="abc123", kind="drop_to_ingest", created_at=2.0)
    )
    reopened = FsIntentStore(tmp_path)
    listed = await reopened.list()
    assert [i.id for i in listed] == ["abc123"]


async def test_replace_marks_resolved(tmp_path):
    store = FsIntentStore(tmp_path)
    intent = Intent(id="r1", kind="drop_to_ingest", status=PENDING, created_at=1.0)
    await store.add(intent)
    intent.status = RESOLVED
    intent.resolved_at = 5.0
    intent.result = {"ok": True}
    await store.replace(intent)
    got = await store.get("r1")
    assert got.status == RESOLVED
    assert got.result == {"ok": True}


async def test_missing_intent_is_none(tmp_path):
    assert await FsIntentStore(tmp_path).get("ghost") is None


async def test_unsafe_id_does_not_escape(tmp_path):
    store = FsIntentStore(tmp_path)
    # A traversal id resolves to None rather than reading outside the dir.
    assert await store.get("../escape") is None


async def test_empty_dir_lists_nothing(tmp_path):
    assert await FsIntentStore(tmp_path).list() == []
