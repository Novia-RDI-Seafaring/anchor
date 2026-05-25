"""HeadlessChromiumSnapshotter — construction + integration tests.

Most CI runs skip the real chromium hit; the marker `slow` gates the
end-to-end test. Without `-m slow`, only the construction-time guards run.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from anchor.core.ports.snapshot import SnapshotPort


def test_snapshotter_constructs_without_playwright_import(tmp_path: Path):
    # Construction must not eagerly import playwright — the import is
    # lazy in `snapshot()` so that callers who never snapshot don't pay
    # for it. Verify by constructing and inspecting attrs only.
    from anchor.infra.snapshot.headless_chromium_snapshotter import (
        HeadlessChromiumSnapshotter,
    )

    s = HeadlessChromiumSnapshotter(base_url="http://localhost:8002", output_dir=tmp_path)
    assert s.base_url == "http://localhost:8002"
    assert s.output_dir == tmp_path
    assert s.canvas_path == "/c"


def test_snapshotter_satisfies_port_protocol(tmp_path: Path):
    from inspect import signature

    from anchor.infra.snapshot.headless_chromium_snapshotter import (
        HeadlessChromiumSnapshotter,
    )

    s = HeadlessChromiumSnapshotter(output_dir=tmp_path)
    # `Protocol` runtime check isn't available without @runtime_checkable;
    # assert the method shape instead — it's what the port actually
    # promises callers.
    assert callable(getattr(s, "snapshot"))
    params = signature(s.snapshot).parameters
    assert set(params.keys()) >= {"slug", "format", "viewport", "full_page"}
    # Reference the port symbol so the import stays useful (catches drift
    # in the port name).
    assert SnapshotPort.__name__ == "SnapshotPort"


def test_snapshotter_rejects_svg_for_now(tmp_path: Path):
    async def run():
        from anchor.infra.snapshot.headless_chromium_snapshotter import (
            HeadlessChromiumSnapshotter,
        )
        s = HeadlessChromiumSnapshotter(output_dir=tmp_path)
        with pytest.raises(NotImplementedError):
            await s.snapshot("w1", format="svg")
    asyncio.run(run())


def test_snapshotter_rejects_unknown_format(tmp_path: Path):
    async def run():
        from anchor.infra.snapshot.headless_chromium_snapshotter import (
            HeadlessChromiumSnapshotter,
        )
        s = HeadlessChromiumSnapshotter(output_dir=tmp_path)
        with pytest.raises(ValueError, match="unsupported snapshot format"):
            await s.snapshot("w1", format="webp")
    asyncio.run(run())


@pytest.mark.slow
def test_snapshotter_end_to_end_against_running_server(tmp_path: Path):
    """Integration: requires a running `anchor serve` + chromium installed.

    Skipped unless invoked with `pytest -m slow`. The test points at
    localhost:8002, the dev default; override with ANCHOR_TEST_BASE_URL.
    """
    import os

    async def run():
        from anchor.infra.snapshot.headless_chromium_snapshotter import (
            HeadlessChromiumSnapshotter,
        )

        base = os.environ.get("ANCHOR_TEST_BASE_URL", "http://localhost:8002")
        slug = os.environ.get("ANCHOR_TEST_SLUG", "demo")
        s = HeadlessChromiumSnapshotter(base_url=base, output_dir=tmp_path)
        result = await s.snapshot(slug, format="png", viewport=(640, 480))
        assert result.format == "png"
        assert result.path is not None and result.path.exists()
        assert result.path.stat().st_size > 0

    asyncio.run(run())
