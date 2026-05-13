"""SnapshotPort backed by a headless chromium via playwright.

This is the *only* file in the repo allowed to import playwright (enforced
by `core_purity` for `anchor.core` and by convention in adapters — they
just call the port). The implementation navigates a running `anchor serve`
to either `/c/<slug>` (full app shell, with chrome) or `/m/<slug>` (the
clean read-only canvas projection if the frontend ships it). We default
to `/c/<slug>` because it always exists; the m/ route is opt-in via the
`canvas_path` constructor arg.

The snapshotter does **not** spawn `anchor serve` for you — running the
HTTP server is a prerequisite. Surfaced as a clean error if chromium
fails to navigate (so the CLI can map it to a 1-liner hint).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from anchor.core.ports.snapshot import SnapshotResult


class HeadlessChromiumSnapshotter:
    """Render a workspace canvas to PNG/SVG via headless chromium.

    Construct with the URL of a running anchor HTTP server and an output
    directory. Each `snapshot(slug)` call writes a timestamped file under
    `output_dir/<slug>/<ts>.<ext>` so successive captures form a visible
    timeline a human can scrub through.
    """

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:8002",
        output_dir: Path,
        canvas_path: str = "/c",
        default_viewport: tuple[int, int] = (1920, 1080),
        nav_timeout_ms: int = 30_000,
        settle_ms: int = 1200,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.output_dir = Path(output_dir)
        self.canvas_path = "/" + canvas_path.strip("/")
        self.default_viewport = default_viewport
        self.nav_timeout_ms = nav_timeout_ms
        self.settle_ms = settle_ms

    async def snapshot(
        self,
        slug: str,
        *,
        format: str = "png",
        viewport: tuple[int, int] | None = None,
        full_page: bool = True,
    ) -> SnapshotResult:
        if format not in {"png", "svg"}:
            raise ValueError(f"unsupported snapshot format: {format!r}")
        # SVG export from React Flow is fiddly (needs a frontend export
        # hook); v1 ships PNG only. The port supports both shapes so we
        # can fill SVG in without churning the rest of the stack.
        if format == "svg":
            raise NotImplementedError(
                "SVG snapshot is not implemented yet — request format='png' "
                "or call the frontend's React Flow export hook directly.",
            )

        # Import here to keep playwright cold-start out of the import
        # graph for callers that don't snapshot (e.g. plain CLI ingest).
        from playwright.async_api import async_playwright

        url = f"{self.base_url}{self.canvas_path}/{slug}"
        w, h = viewport or self.default_viewport

        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        slug_dir = self.output_dir / slug
        slug_dir.mkdir(parents=True, exist_ok=True)
        target = slug_dir / f"{ts}.png"

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(viewport={"width": w, "height": h})
                page = await ctx.new_page()
                await page.goto(url, timeout=self.nav_timeout_ms, wait_until="networkidle")
                # Give React Flow a beat to finish its initial layout +
                # fitView animation. Cheaper than waiting on a custom
                # ready-flag the frontend would have to publish.
                await page.wait_for_timeout(self.settle_ms)
                await page.screenshot(path=str(target), full_page=full_page)
            finally:
                await browser.close()

        return SnapshotResult(format="png", content_type="image/png", path=target)
