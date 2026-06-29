"""Replay events.jsonl → Workspace state on cold boot.

Used by FsWorkspaceStore.load: seed from snapshot, then apply any events
newer than `snapshot.version`.
"""
from __future__ import annotations

import json
from pathlib import Path

from anchor.core.events.canvas import (
    CanvasCleared,
    CanvasSnapshot,
    EdgeAdded,
    EdgeRemoved,
    EdgeUpdated,
    NodeAdded,
    NodeMoved,
    NodeRemoved,
    NodeReparented,
    NodeResized,
    NodeUpdated,
    ReferenceAttached,
    ReferenceCreated,
)
from anchor.core.workspace.reducer import apply
from anchor.core.workspace.workspace import Workspace

_EVENT_TYPES = {
    "NodeAdded": NodeAdded,
    "NodeRemoved": NodeRemoved,
    "NodeMoved": NodeMoved,
    "NodeResized": NodeResized,
    "NodeUpdated": NodeUpdated,
    "NodeReparented": NodeReparented,
    "EdgeAdded": EdgeAdded,
    "EdgeRemoved": EdgeRemoved,
    "EdgeUpdated": EdgeUpdated,
    "CanvasCleared": CanvasCleared,
    "CanvasSnapshot": CanvasSnapshot,
    "ReferenceCreated": ReferenceCreated,
    "ReferenceAttached": ReferenceAttached,
}


def replay_from_events(state: Workspace, events_path: Path) -> Workspace:
    if not events_path.exists():
        return state
    new = state
    base_version = state.version
    with events_path.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            if not raw.strip():
                continue
            rec = json.loads(raw)
            version = int(rec.get("version", 0))
            if version <= base_version:
                continue
            evt_type = rec.get("type")
            payload = rec.get("payload", {})
            cls = _EVENT_TYPES.get(evt_type)
            if cls is None:
                continue
            try:
                evt = cls(**payload)
            except Exception:
                continue
            new = apply(new, evt)
            new.version = version
            new.last_event_id = rec.get("id")
    return new
