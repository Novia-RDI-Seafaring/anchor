"""FsIngestSessionStore - staging layout under <data_dir>/staging/ingest/."""
from __future__ import annotations

import asyncio

import pytest

from anchor.core.upload_safety import UnsafeUploadError
from anchor.extensions.anchor_pdfs.infra.fs_session_store import FsIngestSessionStore


@pytest.fixture
def store(tmp_path):
    return FsIngestSessionStore(tmp_path)


def test_write_read_roundtrip_under_staging(store, tmp_path):
    async def run():
        await store.write_text("ing-abc", "session.json", '{"slug": "demo"}')
        assert await store.read_text("ing-abc", "session.json") == '{"slug": "demo"}'
        target = tmp_path / "staging" / "ingest" / "ing-abc" / "session.json"
        assert target.is_file()
        # No temp file left behind by the atomic replace.
        assert not target.with_name("session.json.tmp").exists()

    asyncio.run(run())


def test_journal_appends_lines(store):
    async def run():
        await store.append_line("ing-abc", "journal.jsonl", '{"op": "begin"}')
        await store.append_line("ing-abc", "journal.jsonl", '{"op": "submit_page"}\n')
        raw = await store.read_text("ing-abc", "journal.jsonl")
        assert raw.splitlines() == ['{"op": "begin"}', '{"op": "submit_page"}']

    asyncio.run(run())


def test_list_session_ids_only_counts_real_sessions(store):
    async def run():
        await store.write_text("ing-b", "session.json", "{}")
        await store.write_text("ing-a", "session.json", "{}")
        await store.write_text("ing-c", "journal.jsonl", "{}")  # no session.json
        assert await store.list_session_ids() == ["ing-a", "ing-b"]

    asyncio.run(run())


def test_delete_staged_keeps_session_and_journal(store):
    async def run():
        await store.write_text("ing-abc", "session.json", "{}")
        await store.append_line("ing-abc", "journal.jsonl", "{}")
        await store.write_text("ing-abc", "gold/pages/1.regions.json", "[]")
        await store.write_text("ing-abc", "silver/pages/1.md", "# md")
        await store.delete_staged("ing-abc")
        assert await store.read_text("ing-abc", "gold/pages/1.regions.json") is None
        assert await store.read_text("ing-abc", "silver/pages/1.md") is None
        assert await store.read_text("ing-abc", "session.json") == "{}"
        assert await store.read_text("ing-abc", "journal.jsonl") is not None

    asyncio.run(run())


def test_rejects_traversal_in_session_id_and_artifact_name(store):
    async def run():
        for bad_sid in ["../escape", "a/b", ".", ""]:
            try:
                await store.write_text(bad_sid, "session.json", "{}")
            except UnsafeUploadError:
                continue
            raise AssertionError(f"session id {bad_sid!r} accepted")
        for bad_name in ["../other/session.json", "/abs/path.json"]:
            try:
                await store.write_text("ing-abc", bad_name, "{}")
            except UnsafeUploadError:
                continue
            raise AssertionError(f"artifact name {bad_name!r} accepted")

    asyncio.run(run())
