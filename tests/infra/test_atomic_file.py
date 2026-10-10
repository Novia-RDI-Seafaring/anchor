"""Windows retry policy preserves atomic publication and permanent failures."""
from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os

import pytest

from anchor.core.workspace.workspace import Workspace
from anchor.extensions.anchor_pdfs.core.source_identity import SourceIdentityError
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.infra import atomic_file
from anchor.infra.stores.fs_workspace_store import FsWorkspaceStore


def _denied(path, winerror=5):
    error = PermissionError(errno.EACCES, "replacement denied", str(path))
    if winerror is not None:
        error.winerror = winerror
    return error


def test_replace_succeeds_without_waiting(tmp_path, monkeypatch):
    source, destination = tmp_path / "new.tmp", tmp_path / "state.json"
    source.write_bytes(b"NEW")
    destination.write_bytes(b"OLD")

    async def unexpected_wait(delay):
        raise AssertionError("Successful replacement must not wait")

    monkeypatch.setattr(atomic_file, "sleep", unexpected_wait)
    asyncio.run(atomic_file.replace_file(source, destination))
    assert destination.read_bytes() == b"NEW"
    assert not source.exists()


def test_transient_denial_preserves_destination_until_replace_succeeds(tmp_path, monkeypatch):
    source, destination = tmp_path / "new.tmp", tmp_path / "state.json"
    source.write_bytes(b"NEW")
    destination.write_bytes(b"OLD")
    real_replace = os.replace
    attempts, waits = [], []

    def denied_twice(src, dst):
        attempts.append((src, dst))
        assert destination.read_bytes() == b"OLD"
        assert source.read_bytes() == b"NEW"
        if len(attempts) <= 2:
            raise _denied(dst)
        real_replace(src, dst)

    async def record_wait(delay):
        waits.append(delay)

    monkeypatch.setattr(atomic_file, "_IS_WINDOWS", True)
    monkeypatch.setattr(atomic_file.os, "replace", denied_twice)
    monkeypatch.setattr(atomic_file, "sleep", record_wait)
    asyncio.run(atomic_file.replace_file(source, destination))
    assert len(attempts) == 3
    assert waits == [0.01, 0.02]
    assert destination.read_bytes() == b"NEW"


@pytest.mark.parametrize("windows,winerror", [(False, 5), (True, None), (True, 2), (True, 32)])
def test_non_windows_or_other_errors_fail_immediately(tmp_path, monkeypatch, windows, winerror):
    error = _denied(tmp_path / "state.json", winerror)
    attempts = []

    def denied(src, dst):
        attempts.append((src, dst))
        raise error

    async def unexpected_wait(delay):
        raise AssertionError("This error must not be retried")

    monkeypatch.setattr(atomic_file, "_IS_WINDOWS", windows)
    monkeypatch.setattr(atomic_file.os, "replace", denied)
    monkeypatch.setattr(atomic_file, "sleep", unexpected_wait)
    with pytest.raises(PermissionError) as caught:
        asyncio.run(atomic_file.replace_file(tmp_path / "new.tmp", tmp_path / "state.json"))
    assert caught.value is error
    assert len(attempts) == 1


def test_exhaustion_is_bounded_and_retains_exception_and_files(tmp_path, monkeypatch):
    source, destination = tmp_path / "new.tmp", tmp_path / "state.json"
    source.write_bytes(b"NEW")
    destination.write_bytes(b"OLD")
    error = _denied(destination)
    attempts, waits = [], []

    def denied(src, dst):
        attempts.append((src, dst))
        raise error

    async def record_wait(delay):
        waits.append(delay)

    monkeypatch.setattr(atomic_file, "_IS_WINDOWS", True)
    monkeypatch.setattr(atomic_file.os, "replace", denied)
    monkeypatch.setattr(atomic_file, "sleep", record_wait)
    with pytest.raises(PermissionError) as caught:
        asyncio.run(atomic_file.replace_file(source, destination))
    assert caught.value is error
    assert len(attempts) == 6
    assert waits == [0.01, 0.02, 0.04, 0.08, 0.16]
    assert sum(waits) == pytest.approx(0.31)
    assert destination.read_bytes() == b"OLD"
    assert source.read_bytes() == b"NEW"


async def _store_writer(tmp_path, kind):
    if kind == "workspace":
        store = FsWorkspaceStore(tmp_path / "canvases")
        await store.create("doc")
        destination = tmp_path / "canvases/doc/state.json"

        async def write():
            await store.snapshot("doc", Workspace(slug="doc", version=42))

        expected = ("version", 42)
    else:
        store = FsDocStore(tmp_path)
        await store.stash_bronze(b"A", "doc.pdf", slug="doc")
        destination = tmp_path / "bronze/doc/original.json"

        async def write():
            path = await store.stash_bronze(b"B", "doc.pdf", slug="doc")
            assert path.read_bytes() == b"B"

        expected = ("sha256", hashlib.sha256(b"B").hexdigest())
    return destination, write, expected


@pytest.mark.parametrize("kind", ["workspace", "bronze"])
def test_stores_retry_and_publish_complete_data(tmp_path, monkeypatch, kind):
    async def run():
        destination, write, expected = await _store_writer(tmp_path, kind)
        before = destination.read_bytes()
        real_replace = os.replace
        attempts = []

        def denied_twice(src, dst):
            if dst == destination:
                attempts.append(src)
                assert destination.read_bytes() == before
                json.loads(src.read_text(encoding="utf-8"))
                if len(attempts) <= 2:
                    raise _denied(dst)
            real_replace(src, dst)

        async def no_wait(delay):
            assert destination.read_bytes() == before

        monkeypatch.setattr(atomic_file, "_IS_WINDOWS", True)
        monkeypatch.setattr(atomic_file.os, "replace", denied_twice)
        monkeypatch.setattr(atomic_file, "sleep", no_wait)
        await write()
        assert len(attempts) == 3
        payload = json.loads(destination.read_text(encoding="utf-8"))
        assert payload[expected[0]] == expected[1]
        assert not list(tmp_path.rglob("*.tmp"))

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["workspace", "bronze"])
@pytest.mark.parametrize("cancel", [False, True])
def test_stores_clean_temps_and_keep_old_publication_on_failure(tmp_path, monkeypatch, kind, cancel):
    async def run():
        destination, write, _ = await _store_writer(tmp_path, kind)
        before = destination.read_bytes()
        error = _denied(destination)
        real_replace = os.replace
        attempts = []

        def denied(src, dst):
            if dst == destination:
                attempts.append(src)
                raise error
            real_replace(src, dst)

        async def wait(delay):
            if cancel:
                raise asyncio.CancelledError

        monkeypatch.setattr(atomic_file, "_IS_WINDOWS", True)
        monkeypatch.setattr(atomic_file.os, "replace", denied)
        monkeypatch.setattr(atomic_file, "sleep", wait)
        expected_error = asyncio.CancelledError if cancel else (
            SourceIdentityError if kind == "bronze" else PermissionError
        )
        with pytest.raises(expected_error) as caught:
            await write()
        if not cancel:
            original = caught.value.__cause__ if kind == "bronze" else caught.value
            assert original is error
        assert len(attempts) == (1 if cancel else 6)
        assert destination.read_bytes() == before
        assert not list(tmp_path.rglob("*.tmp"))

    asyncio.run(run())


@pytest.mark.skipif(os.name != "nt", reason="Real Windows file sharing")
@pytest.mark.parametrize("kind", ["workspace", "bronze"])
def test_real_windows_sharing_releases_while_retry_yields(tmp_path, monkeypatch, kind):
    async def run():
        destination, write, expected = await _store_writer(tmp_path, kind)
        before = destination.read_bytes()
        held = destination.open("rb")
        denial = asyncio.Event()
        real_replace = os.replace

        def observe_denial(src, dst):
            try:
                real_replace(src, dst)
            except OSError as error:
                if dst == destination:
                    assert error.winerror == 5
                    assert destination.read_bytes() == before
                    denial.set()
                raise

        monkeypatch.setattr(atomic_file.os, "replace", observe_denial)

        async def release():
            await denial.wait()
            await asyncio.sleep(0.02)
            held.close()

        task = asyncio.create_task(release())
        try:
            await write()
            assert denial.is_set()
            assert task.done()
            payload = json.loads(destination.read_text(encoding="utf-8"))
            assert payload[expected[0]] == expected[1]
            assert destination.read_bytes() != before
            assert not list(tmp_path.rglob("*.tmp"))
        finally:
            held.close()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.skipif(os.name != "nt", reason="Repeated Windows atomic writes")
@pytest.mark.parametrize("kind", ["workspace", "bronze"])
def test_real_windows_repeated_writes(tmp_path, kind):
    async def run():
        destination, write, expected = await _store_writer(tmp_path, kind)
        for _ in range(100):
            await write()
            payload = json.loads(destination.read_text(encoding="utf-8"))
            assert payload[expected[0]] == expected[1]
        assert not list(tmp_path.rglob("*.tmp"))

    asyncio.run(run())
