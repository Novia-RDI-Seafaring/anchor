"""Source identity across ingestion, persisted reads and source consumers."""
from __future__ import annotations

import asyncio
import hashlib
import json

import pymupdf
import pytest

from anchor.extensions.anchor_pdfs.core.services import IngestService
from anchor.extensions.anchor_pdfs.core.source_identity import SourceIdentityError, original_source
from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
from anchor.extensions.anchor_pdfs.infra.pdf.pymupdf_renderer import PymupdfPdfRenderer
from anchor.infra.bus.memory_bus import MemoryEventBus
from tests.fixtures.fakes import FakePdfExtractor


def pdf_bytes(text):
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 90), text, fontsize=24)
        return pdf.tobytes()


def ingest_service(store):
    return IngestService(store, MemoryEventBus(), extractor=FakePdfExtractor(),
                         renderer=PymupdfPdfRenderer())


def test_same_basename_different_documents_keep_original_bytes_after_restart(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        svc = ingest_service(store)
        original_a, original_b = pdf_bytes("DOCUMENT A"), pdf_bytes("DOCUMENT B")
        await svc.ingest_pdf(original_a, "shared.pdf", slug="doc-a", regions=False)
        await svc.ingest_pdf(original_b, "shared.pdf", slug="doc-b", regions=False)
        for reader in (store, FsDocStore(tmp_path)):
            for slug, expected in (("doc-a", original_a), ("doc-b", original_b)):
                path = await reader.get_raw_pdf_path(slug)
                assert path is not None
                assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(expected).digest()

    asyncio.run(run())


@pytest.mark.parametrize("second_name", ["shared.pdf", "different.pdf", "caf\u00e9.PDF", "cafe\u0301.pdf"])
def test_same_bytes_are_independent_and_repeated_ingest_is_idempotent(tmp_path, second_name):
    async def run():
        store = FsDocStore(tmp_path)
        svc = ingest_service(store)
        raw = pdf_bytes("DOCUMENT A")
        for slug, name in (("doc-a", "shared.pdf"), ("doc-b", second_name), ("doc-a", "shared.pdf")):
            await svc.ingest_pdf(raw, name, slug=slug, regions=False)
        a = await store.get_raw_pdf_path("doc-a")
        b = await store.get_raw_pdf_path("doc-b")
        assert a != b
        assert a.read_bytes() == b.read_bytes() == raw
        assert (await store.get_index("doc-b"))["document"]["filename"] == second_name
    asyncio.run(run())


def test_original_is_available_before_index_and_pending_stash_cannot_retarget_index(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        a, b = pdf_bytes("DOCUMENT A"), pdf_bytes("DOCUMENT B")
        await store.stash_bronze(a, "shared.pdf", slug="doc-a")
        assert (await store.get_raw_pdf_path("doc-a")).read_bytes() == a
        await ingest_service(store).ingest_pdf(a, "shared.pdf", slug="doc-a", regions=False)
        await store.stash_bronze(b, "shared.pdf", slug="doc-a")
        assert (await FsDocStore(tmp_path).get_raw_pdf_path("doc-a")).read_bytes() == a
    asyncio.run(run())


@pytest.mark.parametrize("owners,fingerprints", [(1, False), (1, True), (2, True)])
def test_legacy_read_only_compatibility_requires_proven_ownership(tmp_path, owners, fingerprints):
    async def run():
        store = FsDocStore(tmp_path)
        raw = pdf_bytes("DOCUMENT A")
        legacy = store.bronze / "shared.pdf"
        legacy.write_bytes(raw)
        for i in range(owners):
            document = {"filename": "shared.pdf"}
            if fingerprints:
                document["source_sha256"] = hashlib.sha256(raw).hexdigest()
            await store.write_silver_artifact(f"doc-{i}", "index.json", json.dumps({"document": document}))
        for i in range(owners):
            assert (await store.get_raw_pdf_path(f"doc-{i}")).read_bytes() == raw
        # New writes do not mutate or claim the legacy file.
        await ingest_service(store).ingest_pdf(pdf_bytes("DOCUMENT B"), "new.pdf", slug="new", regions=False)
        assert (await store.get_raw_pdf_path("doc-0")).read_bytes() == raw
        assert legacy.read_bytes() == raw
        assert not (store.bronze / "doc-0").exists()
    asyncio.run(run())


@pytest.mark.parametrize("modern", [False, True])
def test_missing_original_does_not_fall_back_to_another_source(tmp_path, modern):
    async def run():
        store = FsDocStore(tmp_path)
        document = {"filename": "missing.pdf"}
        if modern:
            document["source"] = original_source(pdf_bytes("DOCUMENT A"), "doc-a")
            (store.bronze / "missing.pdf").write_bytes(pdf_bytes("DOCUMENT B"))
        await store.write_silver_artifact("doc-a", "index.json", json.dumps({"document": document}))
        assert await store.get_raw_pdf_path("doc-a") is None
    asyncio.run(run())


@pytest.mark.parametrize("document", [
    {"filename": "../outside.pdf"}, {"filename": "..\\outside.pdf"},
    {"filename": "C:\\outside.pdf"}, {"filename": None},
    {"filename": "shared.pdf", "source": {"slug": "doc-b", "sha256": "a" * 64}},
    {"filename": "shared.pdf", "source": {"slug": "doc-a", "sha256": "../outside"}},
    {"filename": "shared.pdf", "source_sha256": "0" * 64},
])
def test_inconsistent_source_metadata_is_reported_without_paths(tmp_path, document):
    async def run():
        store = FsDocStore(tmp_path)
        (store.bronze / "shared.pdf").write_bytes(pdf_bytes("DOCUMENT A"))
        await store.write_silver_artifact("doc-a", "index.json", json.dumps({"document": document}))
        with pytest.raises(SourceIdentityError) as error:
            await store.get_raw_pdf_path("doc-a")
        assert str(tmp_path) not in str(error.value)
    asyncio.run(run())


@pytest.mark.parametrize("filename,slug", [
    ("../shared.pdf", "doc-a"), ("..\\shared.pdf", "doc-a"), ("C:\\shared.pdf", "doc-a"),
    ("bad\x00.pdf", "doc-a"), ("shared.txt", "doc-a"),
    ("shared.pdf", "../doc-a"), ("shared.pdf", "..\\doc-a"), ("shared.pdf", "C:doc-a"),
])
def test_unsafe_identity_fails_before_publication(tmp_path, filename, slug):
    async def run():
        store = FsDocStore(tmp_path)
        with pytest.raises(ValueError):
            await ingest_service(store).ingest_pdf(pdf_bytes("DOCUMENT A"), filename, slug=slug)
        assert await store.list_documents() == []
        assert await store.list_embeddings() == []
        assert not list(store.bronze.iterdir())
    asyncio.run(run())


def test_conflicting_owner_rejection_leaves_no_partial_target_publication(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        raw = pdf_bytes("DOCUMENT A")
        await ingest_service(store).ingest_pdf(raw, "shared.pdf", slug="doc-a", regions=False)
        # An aliased/copied ownership record must never be silently adopted.
        target = store.bronze / "doc-b"
        target.mkdir()
        (target / "original.json").write_text(json.dumps({"slug": "doc-a"}), encoding="utf-8")
        before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        with pytest.raises(SourceIdentityError):
            await ingest_service(store).ingest_pdf(pdf_bytes("DOCUMENT B"), "shared.pdf", slug="doc-b")
        after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
        assert after == before
        assert (await store.get_raw_pdf_path("doc-a")).read_bytes() == raw
        assert await store.get_index("doc-b") is None
        assert (await store.get_regions("doc-b"))["pages"] == {}
        assert await store.get_embeddings("doc-b") is None
        assert [d["slug"] for d in await store.list_documents()] == ["doc-a"]
    asyncio.run(run())


def test_conflicting_legacy_ownership_does_not_guess_the_surviving_original(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        (store.bronze / "shared.pdf").write_bytes(pdf_bytes("DOCUMENT B"))
        for slug in ("doc-a", "doc-b"):
            await store.write_silver_artifact(slug, "index.json", json.dumps({
                "document": {"filename": "shared.pdf"},
            }))
        for slug in ("doc-a", "doc-b"):
            with pytest.raises(SourceIdentityError, match="legacy"):
                await store.get_raw_pdf_path(slug)

    asyncio.run(run())


@pytest.mark.parametrize("alias", ["DOC-A", "doc-a."])
def test_filesystem_slug_aliases_cannot_replace_an_existing_legacy_document(tmp_path, alias):
    async def run():
        store = FsDocStore(tmp_path)
        raw = pdf_bytes("DOCUMENT A")
        (store.bronze / "shared.pdf").write_bytes(raw)
        await store.write_silver_artifact("doc-a", "index.json", json.dumps({
            "document": {"filename": "shared.pdf"},
        }))
        before = (await store.get_index("doc-a"))
        with pytest.raises(SourceIdentityError):
            await ingest_service(store).ingest_pdf(pdf_bytes("DOCUMENT B"), "shared.pdf", slug=alias)
        assert await store.get_index("doc-a") == before
        assert (await store.get_raw_pdf_path("doc-a")).read_bytes() == raw
    asyncio.run(run())


def test_tampered_authoritative_original_never_falls_back_to_legacy(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        raw = pdf_bytes("DOCUMENT A")
        await ingest_service(store).ingest_pdf(raw, "shared.pdf", slug="doc-a", regions=False)
        path = await store.get_raw_pdf_path("doc-a")
        path.write_bytes(pdf_bytes("DOCUMENT B"))
        (store.bronze / "shared.pdf").write_bytes(raw)
        with pytest.raises(SourceIdentityError):
            await FsDocStore(tmp_path).get_raw_pdf_path("doc-a")
    asyncio.run(run())


@pytest.mark.parametrize("replacement_name", ["shared.pdf", "renamed.pdf"])
def test_reingesting_one_legacy_owner_does_not_erase_conflict_evidence(tmp_path, replacement_name):
    async def run():
        store = FsDocStore(tmp_path)
        raw_b = pdf_bytes("DOCUMENT B")
        (store.bronze / "shared.pdf").write_bytes(raw_b)
        for slug in ("doc-a", "doc-b"):
            await store.write_silver_artifact(slug, "index.json", json.dumps({
                "document": {"filename": "shared.pdf"},
            }))
        await ingest_service(store).ingest_pdf(raw_b, replacement_name, slug="doc-b", regions=False)
        with pytest.raises(SourceIdentityError, match="legacy"):
            await FsDocStore(tmp_path).get_raw_pdf_path("doc-a")
        assert (await store.get_raw_pdf_path("doc-b")).read_bytes() == raw_b
    asyncio.run(run())


@pytest.mark.parametrize("payload", ["{}", "[]", "null", "{broken"])
def test_malformed_index_cannot_resolve_to_pending_source(tmp_path, payload):
    async def run():
        store = FsDocStore(tmp_path)
        raw = pdf_bytes("DOCUMENT A")
        await store.stash_bronze(raw, "shared.pdf", slug="doc-a")
        await store.write_silver_artifact("doc-a", "index.json", payload)
        with pytest.raises(SourceIdentityError):
            await store.get_raw_pdf_path("doc-a")
    asyncio.run(run())


def test_directory_at_source_path_rejects_before_receipt_or_derived_publication(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        raw = pdf_bytes("DOCUMENT A")
        conflict = store.bronze / "doc-a" / f"{hashlib.sha256(raw).hexdigest()}.pdf"
        conflict.mkdir(parents=True)
        with pytest.raises(SourceIdentityError):
            await ingest_service(store).ingest_pdf(raw, "shared.pdf", slug="doc-a")
        assert not (conflict.parent / "original.json").exists()
        assert await store.list_documents() == []
        assert await store.list_ingest_activity() == []
    asyncio.run(run())


def test_legacy_slug_equal_to_filename_remains_readable_but_cannot_be_overwritten(tmp_path):
    async def run():
        store = FsDocStore(tmp_path)
        raw = pdf_bytes("DOCUMENT A")
        (store.bronze / "shared.pdf").write_bytes(raw)
        await store.write_silver_artifact("shared.pdf", "index.json", json.dumps({
            "document": {"filename": "shared.pdf"},
        }))
        assert (await store.get_raw_pdf_path("shared.pdf")).read_bytes() == raw
        with pytest.raises(SourceIdentityError):
            await ingest_service(store).ingest_pdf(pdf_bytes("DOCUMENT B"), "shared.pdf", slug="shared.pdf")
        assert (await store.get_raw_pdf_path("shared.pdf")).read_bytes() == raw
    asyncio.run(run())
