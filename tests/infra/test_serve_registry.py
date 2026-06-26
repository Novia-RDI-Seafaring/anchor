"""Runtime serve registry: ties a running serve's port to its project.

Covers #177 / #179 -- discovering which `anchor serve` (port) hosts a given
project so a canvas URL is not a guessed :8002.
"""
from __future__ import annotations

import json
import os

import pytest

from anchor.infra import environment as env_mod
from anchor.infra import serve_registry as sr
from anchor.infra.environment import create_env, create_project, identify_data_dir


@pytest.fixture(autouse=True)
def _home(monkeypatch, tmp_path):
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_CONFIG", "ANCHOR_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def test_identify_data_dir_reads_marker(tmp_path):
    env = create_env("work", settings={"provider": "local"})
    folder = tmp_path / "pumps"
    create_project(env, "pumps", root=folder)
    env_name, project = identify_data_dir(folder / ".anchor_data")
    assert env_name == "work"
    assert project == "pumps"


def test_identify_data_dir_unmarked_is_unknown(tmp_path):
    env_name, project = identify_data_dir(tmp_path / "loose" / ".anchor_data")
    assert env_name is None
    assert project is None


def test_register_writes_self_describing_record(tmp_path):
    env = create_env("work", settings={"provider": "local"})
    folder = tmp_path / "pumps"
    create_project(env, "pumps", root=folder)
    data_dir = folder / ".anchor_data"

    path = sr.register_serve(
        host="127.0.0.1", port=8003, data_dir=data_dir, started_at="2026-06-26T00:00:00Z"
    )
    try:
        record = json.loads(path.read_text())
        assert record["port"] == 8003
        assert record["env"] == "work"
        assert record["project"] == "pumps"
        assert record["pid"] == os.getpid()

        found = sr.find_serve_for_data_dir(data_dir)
        assert found is not None
        assert found.base_url() == "http://127.0.0.1:8003"
    finally:
        sr.unregister_serve(path)
    assert sr.find_serve_for_data_dir(data_dir) is None


def test_find_serve_distinguishes_projects(tmp_path, monkeypatch):
    # Two serves are two processes -> distinct pid-keyed records. Simulate the
    # second process's pid so both records coexist (one process only ever owns
    # one serve, which is the real-world invariant).
    env = create_env("work", settings={"provider": "local"})
    a = tmp_path / "alpha"
    b = tmp_path / "beta"
    create_project(env, "alpha", root=a)
    create_project(env, "beta", root=b)
    real_pid = os.getpid()
    pa = sr.register_serve(
        host="127.0.0.1", port=8002, data_dir=a / ".anchor_data", started_at="t"
    )
    # Reuse a live pid (the parent of this test process) for the second record
    # so it is not pruned as stale; only the filename needs to differ.
    other_pid = os.getppid() or real_pid
    monkeypatch.setattr(sr.os, "getpid", lambda: other_pid)
    pb = sr.register_serve(
        host="127.0.0.1", port=8003, data_dir=b / ".anchor_data", started_at="t"
    )
    monkeypatch.setattr(sr.os, "getpid", lambda: real_pid)
    try:
        # The project on the bumped port is found at its real port, not :8002.
        assert sr.find_serve_for_data_dir(b / ".anchor_data").port == 8003
        assert sr.find_serve_for_data_dir(a / ".anchor_data").port == 8002
    finally:
        sr.unregister_serve(pa)
        sr.unregister_serve(pb)


def test_stale_dead_pid_record_is_pruned(tmp_path):
    # A record whose PID is not alive (crash without cleanup) must never be
    # reported as a running serve.
    sr.serves_dir().mkdir(parents=True, exist_ok=True)
    dead = sr.serves_dir() / "999999.json"
    dead.write_text(json.dumps({
        "pid": 999999, "host": "127.0.0.1", "port": 8099,
        "data_dir": str(tmp_path), "env": "x", "project": "y", "started_at": "t",
    }))
    assert sr.list_serves() == []
    assert not dead.exists()  # pruned on read
    assert sr.find_serve_for_data_dir(tmp_path) is None


def test_url_host_rewrites_wildcard_bind(tmp_path):
    path = sr.register_serve(
        host="0.0.0.0", port=8005, data_dir=tmp_path, started_at="t"
    )
    try:
        record = sr.find_serve_for_data_dir(tmp_path)
        assert record.base_url() == "http://127.0.0.1:8005"
    finally:
        sr.unregister_serve(path)
