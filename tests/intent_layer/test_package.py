"""Canonical compatibility and actual distributable independence."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from intent_layer import actor, models, ports
from intent_layer.errors import ThreadError
from intent_layer.fs_store import FsIntentStore, UnsafeIntentIdError
from intent_layer.memory_store import MemoryIntentStore

ROOT = Path(__file__).resolve().parents[2]


def test_anchor_reexports_canonical_actor_models_errors_and_ports():
    from anchor.core.events import actor as anchor_actor
    from anchor.core.intents import intent as anchor_model
    from anchor.core.ports import thread_host
    from anchor.core.services.intent_service import ThreadError as AnchorThreadError
    from anchor.infra.stores.memory_intent_store import MemoryIntentStore as AnchorMemory

    assert anchor_actor.Actor is actor.Actor
    assert anchor_actor.current_actor is actor.current_actor
    assert anchor_actor.set_current_actor is actor.set_current_actor
    assert anchor_actor.reset_current_actor is actor.reset_current_actor
    assert anchor_actor.actor_scope is actor.actor_scope
    assert anchor_model.Intent is models.Intent
    assert anchor_model.ThreadItem is models.ThreadItem
    assert AnchorThreadError is ThreadError
    assert thread_host.ThreadHost is ports.ThreadHost
    assert thread_host.ThreadContext is ports.ThreadContext
    assert AnchorMemory is MemoryIntentStore
    with actor.actor_scope(actor.Actor(kind="agent", id="shared")):
        assert anchor_actor.current_actor() is actor.current_actor()
    with anchor_actor.actor_scope(actor.Actor(kind="human", id="same-context")):
        assert actor.current_actor().id == "same-context"


async def test_generic_and_anchor_unsafe_id_behavior(tmp_path):
    from anchor.core.upload_safety import UnsafeUploadError
    from anchor.infra.stores.fs_intent_store import FsIntentStore as AnchorFs

    for store, error in [(FsIntentStore(tmp_path), UnsafeIntentIdError),
                         (AnchorFs(tmp_path), UnsafeUploadError)]:
        for ident in ("../escape", "..", "a/b", "a\\b", "", "a" * 129):
            assert await store.get(ident) is None
            with pytest.raises(error):
                store._path(ident)
        assert store._path("valid-ID_1").name == "valid-ID_1.json"


def assert_independent_import(path):
    script = r'''
import importlib.abc
import sys
sys.path.insert(0, sys.argv[1])
class NoAnchor(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "anchor" or fullname.startswith("anchor."):
            raise AssertionError("intent_layer attempted to import Anchor: " + fullname)
sys.meta_path.insert(0, NoAnchor())
import intent_layer
import intent_layer.actor
import intent_layer.models
import intent_layer.ports
import intent_layer.service
import intent_layer.fs_store
import intent_layer.memory_store
import intent_layer.signals
import intent_layer.adapters.http
import intent_layer.adapters.mcp
import intent_layer.adapters.cli
assert not any(name == "anchor" or name.startswith("anchor.") for name in sys.modules)
for name, module in tuple(sys.modules.items()):
    if name == "intent_layer" or name.startswith("intent_layer."):
        assert module.__file__.startswith(sys.argv[1]), (name, module.__file__, sys.argv[1])
print("independent imports passed")
'''
    result = subprocess.run([sys.executable, "-I", "-c", script, str(path)],
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_source_imports_without_anchor():
    assert_independent_import(ROOT / "src")


def test_built_wheel_and_sdist_include_independent_namespace(tmp_path):
    # Build real Hatch artifacts using a tiny frontend fixture. This validates
    # packaging without rebuilding unrelated UI assets or changing their hook.
    source, dist = tmp_path / "build-source", tmp_path / "dist"
    source.mkdir()
    shutil.copytree(ROOT / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "hatch_build.py", "README.md", "LICENSE"):
        shutil.copy2(ROOT / name, source / name)
    (source / "web" / "dist").mkdir(parents=True)
    (source / "web" / "dist" / "index.html").write_text("<!doctype html><title>build fixture</title>", encoding="utf-8")
    result = subprocess.run(["uv", "build", "--offline", "--out-dir", str(dist)],
                            cwd=source, text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    wheel = next(dist.glob("*.whl"))
    with zipfile.ZipFile(wheel) as artifact:
        members = set(artifact.namelist())
        for module in ("__init__", "models", "service", "ports", "actor", "signals", "fs_store"):
            assert f"intent_layer/{module}.py" in members
        assert "anchor/core/services/anchor_thread_host.py" in members
        assert "anchor/_web_dist/index.html" in members
    assert_independent_import(wheel)
    with tarfile.open(next(dist.glob("*.tar.gz"))) as artifact:
        members = artifact.getnames()
        assert any(name.endswith("/src/intent_layer/service.py") for name in members)
        assert any(name.endswith("/src/intent_layer/adapters/http.py") for name in members)
        assert any(name.endswith("/src/anchor/core/services/anchor_thread_host.py") for name in members)
