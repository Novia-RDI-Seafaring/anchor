"""Protocol for synopsis renderers (PDF, Marp, ...).

Core defines the contract; infra implements with concrete tools
(pymupdf, plain markdown). Keeps the orchestrating ``SynopsisService``
independent of any specific output stack.
"""
from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, Protocol

from anchor.extensions.anchor_pdfs.core.synopsis import SynopsisData


CropPathResolver = Callable[[str, str], Awaitable[Path | None]]


class PdfSynopsisRenderer(Protocol):
    async def render_pdf(
        self, data: SynopsisData, *, resolve_crop: CropPathResolver,
    ) -> bytes: ...


class MarkdownSynopsisRenderer(Protocol):
    def render_markdown(
        self, data: SynopsisData, *, crop_url_for: Callable[[str, str], str] | None = None,
    ) -> str: ...


__all__ = ["PdfSynopsisRenderer", "MarkdownSynopsisRenderer", "CropPathResolver"]
