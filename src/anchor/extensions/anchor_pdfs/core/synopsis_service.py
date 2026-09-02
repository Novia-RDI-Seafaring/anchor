"""Entity-scoped document synopsis orchestration."""

from __future__ import annotations

from anchor.extensions.anchor_pdfs.core.ports.doc_store import DocStore
from anchor.extensions.anchor_pdfs.core.ports.synopsis_renderer import (
    MarkdownSynopsisRenderer,
    PdfSynopsisRenderer,
)
from anchor.extensions.anchor_pdfs.core.synopsis import SynopsisData, compose_synopsis


class SynopsisService:
    """Compose filtered facts and delegate output to a synopsis renderer."""

    def __init__(
        self,
        store: DocStore,
        *,
        pdf_renderer: PdfSynopsisRenderer | None = None,
        md_renderer: MarkdownSynopsisRenderer | None = None,
    ) -> None:
        self.store = store
        self.pdf_renderer = pdf_renderer
        self.md_renderer = md_renderer

    async def compose(self, *, slug: str, entity: str) -> SynopsisData:
        return await compose_synopsis(store=self.store, slug=slug, entity=entity)

    async def render_pdf(self, *, slug: str, entity: str) -> bytes:
        if self.pdf_renderer is None:
            raise RuntimeError("SynopsisService: no pdf_renderer wired")
        data = await self.compose(slug=slug, entity=entity)
        return await self.pdf_renderer.render_pdf(
            data,
            resolve_crop=self.store.get_crop_path,
        )

    async def render_markdown(
        self,
        *,
        slug: str,
        entity: str,
        crop_url_base: str | None = None,
    ) -> str:
        if self.md_renderer is None:
            raise RuntimeError("SynopsisService: no md_renderer wired")
        data = await self.compose(slug=slug, entity=entity)
        if crop_url_base is None:
            crop_url_for = None
        else:

            def crop_url_for(document_slug: str, relative_path: str) -> str:
                base = crop_url_base.rstrip("/")
                return f"{base}/{document_slug}/crops/{relative_path}"

        return self.md_renderer.render_markdown(data, crop_url_for=crop_url_for)
