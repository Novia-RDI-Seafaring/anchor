"""MCP canvas_snapshot tool — handlers_canvas.call_tool direct.

Uses a fake SnapshotPort. Verifies the byte-envelope contract
(`path`-or-`base64`) matches the existing get_page_image/get_crop shape.
"""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

from anchor.adapters.mcp import handlers_canvas
from tests.fixtures.fakes import TINY_PNG_BYTES, FakeSnapshotter
from tests.fixtures.services import make_in_memory_services


def test_canvas_snapshot_returns_path_envelope(tmp_path: Path):
    async def run():
        s = make_in_memory_services()
        s.workspace.snapshotter = FakeSnapshotter(mode="path", out_dir=tmp_path)
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_snapshot",
            {"workspace_slug": "w1", "format": "path"},
        )
        out = json.loads(body)
        assert out["format"] == "path"
        assert out["content_type"] == "image/png"
        assert Path(out["value"]).exists()
        assert out["size_bytes"] == len(TINY_PNG_BYTES)
    asyncio.run(run())


def test_canvas_snapshot_returns_base64_envelope():
    async def run():
        s = make_in_memory_services()
        s.workspace.snapshotter = FakeSnapshotter(mode="bytes")
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_snapshot",
            {"workspace_slug": "w1", "format": "base64"},
        )
        out = json.loads(body)
        assert out["format"] == "base64"
        assert out["content_type"] == "image/png"
        assert base64.b64decode(out["value"]) == TINY_PNG_BYTES
        assert out["size_bytes"] == len(TINY_PNG_BYTES)
    asyncio.run(run())


def test_canvas_snapshot_inline_bytes_with_path_format_errors():
    # If the snapshotter returned bytes but the agent asked for a path,
    # surface the mismatch instead of pretending there's a file.
    async def run():
        s = make_in_memory_services()
        s.workspace.snapshotter = FakeSnapshotter(mode="bytes")
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_snapshot",
            {"workspace_slug": "w1", "format": "path"},
        )
        assert "error" in json.loads(body)
    asyncio.run(run())


def test_canvas_snapshot_without_snapshotter_returns_error():
    async def run():
        s = make_in_memory_services()  # no snapshotter
        await s.workspace.create_workspace("w1")
        body = await handlers_canvas.call_tool(
            s.workspace, "canvas_snapshot",
            {"workspace_slug": "w1", "format": "path"},
        )
        assert "no snapshotter" in json.loads(body)["error"]
    asyncio.run(run())


def test_canvas_snapshot_forwards_viewport_and_full_page():
    async def run():
        snap = FakeSnapshotter(mode="bytes")
        s = make_in_memory_services()
        s.workspace.snapshotter = snap
        await s.workspace.create_workspace("w1")
        await handlers_canvas.call_tool(
            s.workspace, "canvas_snapshot",
            {
                "workspace_slug": "w1",
                "format": "base64",
                "viewport": [1024, 768],
                "full_page": False,
            },
        )
        assert snap.calls == [
            {"slug": "w1", "format": "png", "viewport": (1024, 768), "full_page": False},
        ]
    asyncio.run(run())


def test_canvas_snapshot_listed_in_tool_definitions():
    defs = handlers_canvas.tool_definitions()
    names = {d["name"] for d in defs}
    assert "canvas_snapshot" in names
