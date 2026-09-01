"""FsDocStore read paths refuse traversal slugs (CodeQL py/path-injection).

Slugs arrive from HTTP / MCP / CLI arguments, so `<layer>/<slug>/...` is a
path-injection sink. The store rejects path components and traversal tokens
and asserts the resolved directory stays under the layer root.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from anchor.core.upload_safety import UnsafeUploadError
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore


@pytest.mark.parametrize("slug", ["../etc", "..", ".", "a/b", "a\\b", ""])
def test_read_paths_reject_traversal_slugs(tmp_path, slug):
    store = FsDocStore(tmp_path)

    async def run():
        for call in (
            lambda: store.get_page_text(slug, 1),
            lambda: store.get_page_image_path(slug, 1),
            lambda: store.get_page_candidates(slug, 1),
            lambda: store.get_regions(slug),
        ):
            with pytest.raises(UnsafeUploadError):
                await call()

    asyncio.run(run())


def test_read_paths_still_resolve_a_normal_slug(tmp_path):
    store = FsDocStore(tmp_path)
    pages = tmp_path / "silver" / "lkh" / "pages"
    pages.mkdir(parents=True)
    (pages / "1.md").write_text("# p1", encoding="utf-8")
    (pages / "1.candidates.json").write_text(json.dumps([{"id": "p1-i0"}]), encoding="utf-8")

    async def run():
        assert await store.get_page_text("lkh", 1) == "# p1"
        assert await store.get_page_candidates("lkh", 1) == [{"id": "p1-i0"}]
        assert await store.get_page_image_path("lkh", 1) is None
        assert (await store.get_regions("lkh"))["pages"] == {}

    asyncio.run(run())
