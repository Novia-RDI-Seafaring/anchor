"""SnapshotPort — render a workspace canvas to bytes (PNG/SVG).

The canvas is rendered by the *frontend* (React Flow). To turn that into a
flat image the system has to drive a browser, but CORE must not know that —
hence this port. Infra wires up a headless-chromium implementation
(`anchor.infra.snapshot.headless_chromium_snapshotter`); tests inject a
fake that returns a pre-canned blob.

The result envelope mirrors the byte-fetch shape already used elsewhere
(`anchor_pdfs.mcp_handlers._byte_envelope`):
  - `path`: the snapshot was written to disk; caller reads bytes itself.
  - inline `bytes`: in-memory blob the adapter base64-encodes for off-host
    callers.

A SnapshotPort implementation may return *either* a path or inline bytes
depending on its constructor wiring. The default infra adapter writes to
disk so successive snapshots accumulate as a visible timeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class SnapshotResult:
    """Outcome of a snapshot. Exactly one of `path` / `bytes_` is set."""

    format: str  # "png" or "svg"
    content_type: str  # "image/png" or "image/svg+xml"
    path: Path | None = None
    bytes_: bytes | None = None

    def __post_init__(self) -> None:
        # Exactly-one invariant — implementations that violate this would
        # surface as confusing 500s downstream, so fail fast.
        if (self.path is None) == (self.bytes_ is None):
            raise ValueError("SnapshotResult requires exactly one of `path` or `bytes_`.")


class SnapshotPort(Protocol):
    async def snapshot(
        self,
        slug: str,
        *,
        format: str = "png",
        viewport: tuple[int, int] | None = None,
        full_page: bool = True,
    ) -> SnapshotResult:
        """Render the workspace `slug` to an image.

        - `format`: "png" (default) or "svg".
        - `viewport`: `(width, height)` in CSS pixels. None = implementation
          default (the canvas at its natural size).
        - `full_page`: capture the whole document, not just the viewport.
        """
        raise NotImplementedError
