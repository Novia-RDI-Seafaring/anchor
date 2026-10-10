"""FsDocStore read paths refuse traversal slugs (CodeQL py/path-injection).

Slugs arrive from HTTP / MCP / CLI arguments, so `<layer>/<slug>/...` is a
path-injection sink. The store rejects path components and traversal tokens
and asserts the resolved directory stays under the layer root.
"""
from __future__ import annotations

import asyncio
import json
import sys

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
            lambda: store.get_pages_meta(slug),
            lambda: store.get_gold_map(slug),
            lambda: store.mark_gold_complete(slug, {}),
            lambda: store.clear_gold_complete(slug),
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


def test_gold_document_link_cannot_read_outside_storage(tmp_path):
    store = FsDocStore(tmp_path / "store")
    outside = tmp_path / "outside"
    (outside / "pages").mkdir(parents=True)
    payload = json.dumps({"page": 1, "regions": [{"id": "r1", "content": "outside"}]})
    (outside / "pages" / "1.regions.json").write_text(payload, encoding="utf-8")
    try:
        (store.gold / "doc").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    with pytest.raises(UnsafeUploadError):
        asyncio.run(store.get_regions("doc"))


@pytest.mark.parametrize("slug", ["../etc", "..", ".", "a/b", "a\\b", "", "C:/outside"])
def test_knowledge_operations_reject_traversal_slugs(tmp_path, slug):
    store = FsDocStore(tmp_path)

    async def run():
        for call in (
            lambda: store.get_regions(slug),
            lambda: store.get_source_regions(slug),
            lambda: store.add_derived_region(slug, {"id": "child", "page": 1, "derived_from": "p1/r1"}),
            lambda: store.remove_derived_region(slug, 1, "child"),
        ):
            with pytest.raises(UnsafeUploadError):
                await call()

    asyncio.run(run())
    assert not list(store.knowledge.glob("**/*.regions.json"))


@pytest.mark.parametrize("link_kind", ["document", "pages", "file"])
def test_knowledge_links_cannot_read_write_or_remove_outside_storage(tmp_path, link_kind):
    store = FsDocStore(tmp_path / "store")
    outside = tmp_path / "outside"
    (outside / "pages").mkdir(parents=True)
    payload = json.dumps({"page": 1, "regions": [{
        "id": "child", "content": "outside", "derived_from": "p1/r1",
    }]})
    outside_file = outside / "pages/1.regions.json"
    outside_file.write_text(payload, encoding="utf-8")
    store.knowledge.mkdir()
    doc = store.knowledge / "doc"
    try:
        if link_kind == "document":
            doc.symlink_to(outside, target_is_directory=True)
        elif link_kind == "pages":
            doc.mkdir()
            (doc / "pages").symlink_to(outside / "pages", target_is_directory=True)
        else:
            (doc / "pages").mkdir(parents=True)
            (doc / "pages/1.regions.json").symlink_to(outside_file)
    except OSError:
        pytest.skip("symlinks are unavailable")

    async def run():
        for call in (
            lambda: store.get_regions("doc"),
            lambda: store.add_derived_region("doc", {"id": "child", "page": 1, "derived_from": "p1/r1"}),
            lambda: store.remove_derived_region("doc", 1, "child"),
        ):
            with pytest.raises(UnsafeUploadError):
                await call()

    asyncio.run(run())
    assert outside_file.read_text(encoding="utf-8") == payload


@pytest.mark.skipif(sys.platform == "win32", reason="Windows cannot create a directory with a literal backslash")
def test_list_documents_skips_a_directory_that_is_not_a_valid_slug(tmp_path):
    # list_documents feeds each silver directory name through the slug guard.
    # A name the guard rejects cannot be a document; it must be skipped, not
    # fail the listing for every other document.
    store = FsDocStore(tmp_path)
    good = tmp_path / "silver" / "lkh"
    good.mkdir(parents=True)
    (good / "index.json").write_text(
        json.dumps({"document": {"title": "LKH", "page_count": 2}}), encoding="utf-8"
    )
    (tmp_path / "silver" / "bad\\name").mkdir()

    docs = asyncio.run(store.list_documents())

    assert [d["slug"] for d in docs] == ["lkh"]
    assert docs[0]["page_count"] == 2
