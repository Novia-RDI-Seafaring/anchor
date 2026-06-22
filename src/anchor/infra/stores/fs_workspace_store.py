"""Filesystem-backed WorkspaceStore.

Layout per workspace:
    canvases/<slug>/
        meta.json            # WorkspaceMeta as JSON
        state.json           # latest snapshot
        events.jsonl         # append-only log; one DomainEvent JSON per line
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path

import aiofiles

from anchor.core.events.envelope import DomainEvent
from anchor.core.ids import validate_workspace_slug
from anchor.core.upload_safety import assert_within
from anchor.core.workspace.workspace import Workspace, WorkspaceMeta


class FsWorkspaceStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._versions: dict[str, int] = {}
        self._seen_ids: dict[str, dict[str, int]] = {}
        self._lock = asyncio.Lock()

    def _slug_dir(self, slug: str) -> Path:
        # Defence-in-depth: even if a caller skipped boundary validation,
        # we refuse to construct a path outside the canvases root.
        validate_workspace_slug(slug)
        target = self.root / slug
        # ``resolve(strict=False)`` follows existing symlinks but does not
        # error on missing trailing segments — exactly what we want for a
        # workspace that hasn't been created yet.
        assert_within(target, self.root)
        return target

    async def list_workspaces(self) -> list[WorkspaceMeta]:
        out: list[WorkspaceMeta] = []
        for p in sorted(self.root.glob("*/meta.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(WorkspaceMeta(**data))
        return out

    async def create(self, slug: str, title: str = "") -> WorkspaceMeta:
        d = self._slug_dir(slug)
        meta_path = d / "meta.json"
        if meta_path.exists():
            return WorkspaceMeta(**json.loads(meta_path.read_text(encoding="utf-8")))
        d.mkdir(parents=True, exist_ok=True)
        meta = WorkspaceMeta(slug=slug, title=title or slug, created_at=time.time())
        await self._atomic_write_text(meta_path, meta.model_dump_json(indent=2))
        await self._atomic_write_text(
            d / "state.json",
            Workspace(slug=slug, title=meta.title).model_dump_json(indent=2),
        )
        (d / "events.jsonl").touch()
        return meta

    async def delete(self, slug: str) -> None:
        d = self._slug_dir(slug)
        async with self._lock:
            meta_path = d / "meta.json"
            if not meta_path.exists():
                raise FileNotFoundError(f"workspace {slug!r} does not exist")
            resolved = assert_within(d, self.root)
            shutil.rmtree(resolved)
            self._versions.pop(slug, None)
            self._seen_ids.pop(slug, None)

    async def load(self, slug: str) -> Workspace:
        d = self._slug_dir(slug)
        if not (d / "meta.json").exists():
            await self.create(slug)
        snap_path = d / "state.json"
        ws = Workspace.model_validate_json(snap_path.read_text(encoding="utf-8"))
        # Replay any events newer than the snapshot.
        events_path = d / "events.jsonl"
        if events_path.exists():
            from anchor.infra.bus.replay import replay_from_events
            ws = replay_from_events(ws, events_path)
        async with self._lock:
            self._versions[slug] = max(self._versions.get(slug, 0), ws.version)
            self._seen_ids.setdefault(slug, {})
        return ws

    async def append_event(self, slug: str, event: DomainEvent) -> int:
        d = self._slug_dir(slug)
        if not (d / "meta.json").exists():
            await self.create(slug)
        async with self._lock:
            seen = self._seen_ids.setdefault(slug, await self._load_seen(slug))
            if event.id in seen:
                return seen[event.id]
            self._versions[slug] = self._versions.get(slug, await self._read_version(slug)) + 1
            event.version = self._versions[slug]
            event.workspace_id = slug
            line = event.model_dump_json() + "\n"
            async with aiofiles.open(d / "events.jsonl", "a", encoding="utf-8") as f:
                await f.write(line)
            seen[event.id] = event.version
            return event.version

    async def snapshot(self, slug: str, state: Workspace) -> None:
        d = self._slug_dir(slug)
        await self._atomic_write_text(d / "state.json", state.model_dump_json(indent=2))

    async def rename(self, slug: str, *, title: str) -> WorkspaceMeta:
        """Update only the display title in meta.json. The slug (directory
        name) is immutable — it's a stable id referenced from other
        canvases via `data.canvas_slug` on canvas-typed nodes, so we
        never rewrite it.

        Idempotent: writing the same title is a no-op."""
        d = self._slug_dir(slug)
        meta_path = d / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"workspace {slug!r} does not exist")
        meta = WorkspaceMeta(**json.loads(meta_path.read_text(encoding="utf-8")))
        if meta.title == title:
            return meta
        meta = WorkspaceMeta(slug=meta.slug, title=title, created_at=meta.created_at)
        await self._atomic_write_text(meta_path, meta.model_dump_json(indent=2))
        # Mirror the title into the snapshot so subsequent loads see it
        # without a replay. Don't touch state.json's nodes/edges/version.
        snap_path = d / "state.json"
        if snap_path.exists():
            ws = Workspace.model_validate_json(snap_path.read_text(encoding="utf-8"))
            if ws.title != title:
                ws.title = title
                await self._atomic_write_text(snap_path, ws.model_dump_json(indent=2))
        return meta

    # ── internals ─────────────────────────────────────────────────────────
    async def _atomic_write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(content)
        os.replace(tmp, path)

    async def _read_version(self, slug: str) -> int:
        events_path = self._slug_dir(slug) / "events.jsonl"
        if not events_path.exists():
            return 0
        # last line's version
        last_version = 0
        with events_path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                last_version = max(last_version, int(json.loads(line).get("version", 0)))
        return last_version

    async def _load_seen(self, slug: str) -> dict[str, int]:
        events_path = self._slug_dir(slug) / "events.jsonl"
        seen: dict[str, int] = {}
        if not events_path.exists():
            return seen
        with events_path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                seen[rec["id"]] = int(rec.get("version", 0))
        return seen
