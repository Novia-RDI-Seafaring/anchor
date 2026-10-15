"""FsIngestSessionStore - staging layout under <data_dir>/staging/ingest/."""
from __future__ import annotations

import asyncio
import errno
import json
import os

import pytest

from anchor.core.upload_safety import UnsafeUploadError
from anchor.extensions.anchor_pdfs.infra.fs_session_store import FsIngestSessionStore
from anchor.infra import atomic_file


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


def _denied(path):
    error = PermissionError(errno.EACCES, "replacement denied", str(path))
    error.winerror = 5
    return error


def test_session_write_retries_transient_denial_and_publishes_complete_json(store, monkeypatch):
    async def run():
        before = {"slug": "demo", "pages": [{"page": 1, "status": "pending"}]}
        updated = {"slug": "demo", "pages": [{"page": 1, "status": "submitted"}]}
        await store.write_text("ing-abc", "session.json", json.dumps(before))
        target = store.root / "ing-abc" / "session.json"
        temporary = target.with_name("session.json.tmp")
        old_bytes = target.read_bytes()
        real_replace = os.replace
        attempts, waits = [], []

        def denied_twice(source, destination):
            assert source == temporary and destination == target
            attempts.append((source, destination))
            assert target.read_bytes() == old_bytes
            assert json.loads(source.read_text(encoding="utf-8")) == updated
            if len(attempts) <= 2:
                raise _denied(destination)
            real_replace(source, destination)

        async def record_wait(delay):
            waits.append(delay)
            assert target.read_bytes() == old_bytes

        monkeypatch.setattr(atomic_file, "_IS_WINDOWS", True)
        monkeypatch.setattr(atomic_file.os, "replace", denied_twice)
        monkeypatch.setattr(atomic_file, "sleep", record_wait)
        await store.write_text("ing-abc", "session.json", json.dumps(updated))

        assert len(attempts) == 3
        assert waits == [0.01, 0.02]
        assert json.loads(await store.read_text("ing-abc", "session.json")) == updated
        assert not temporary.exists()

    asyncio.run(run())


def test_session_write_exhaustion_preserves_old_session_and_failed_temp(store, monkeypatch):
    async def run():
        before = {"slug": "demo", "state": "open"}
        updated = {"slug": "demo", "state": "finalized"}
        await store.write_text("ing-abc", "session.json", json.dumps(before))
        target = store.root / "ing-abc" / "session.json"
        temporary = target.with_name("session.json.tmp")
        old_bytes = target.read_bytes()
        error = _denied(target)
        attempts, waits = [], []

        def denied(source, destination):
            attempts.append((source, destination))
            assert source == temporary and destination == target
            assert target.read_bytes() == old_bytes
            assert json.loads(source.read_text(encoding="utf-8")) == updated
            raise error

        async def record_wait(delay):
            waits.append(delay)
            assert target.read_bytes() == old_bytes

        monkeypatch.setattr(atomic_file, "_IS_WINDOWS", True)
        monkeypatch.setattr(atomic_file.os, "replace", denied)
        monkeypatch.setattr(atomic_file, "sleep", record_wait)
        with pytest.raises(PermissionError) as caught:
            await store.write_text("ing-abc", "session.json", json.dumps(updated))

        assert caught.value is error
        assert len(attempts) == 6
        assert waits == [0.01, 0.02, 0.04, 0.08, 0.16]
        assert await store.read_text("ing-abc", "session.json") == json.dumps(before)
        assert json.loads(temporary.read_text(encoding="utf-8")) == updated

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
