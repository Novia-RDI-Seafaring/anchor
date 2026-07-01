"""No-key gold-skip note on MCP ``ingest_pdf`` (issue #226).

When ``ingest_pdf`` runs but the environment has no vision provider/key wired
(``region_extractor`` is None), the gold stage is silently skipped and the
result reads as a bland success with zero regions. The handler must attach a
machine- and human-readable note that points at the offline harness ingest
path and the endpoint-key remedy. The note is factored into a small pure
helper so it can be unit-tested directly.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool, gold_skipped_note


def test_gold_skipped_note_names_offline_path_and_key_remedy():
    note = gold_skipped_note()
    assert note["gold_skipped"] is True
    blob = json.dumps(note)
    # Offline, key-free harness ingest chain.
    for tool in (
        "ingest_begin", "ingest_get_page", "ingest_submit_page", "ingest_finalize",
    ):
        assert tool in blob
    # Endpoint-key remedy: the exact var, that a plain key is ignored, and check.
    assert "ANCHOR_OPENAI_API_KEY" in blob
    assert "OPENAI_API_KEY there is ignored" in blob
    assert "anchor check" in blob


class _FakeIngest:
    """Minimal stand-in for IngestService for the handler branch under test."""

    def __init__(self, *, region_extractor, summary):
        self.region_extractor = region_extractor
        self._summary = summary

    async def ingest_pdf(self, *args, **kwargs):
        return dict(self._summary)


def _run(coro):
    return asyncio.run(coro)


def _call_ingest(ingest, pdf_path, **args):
    return json.loads(
        _run(call_tool(ingest, store=None, name="ingest_pdf",
                       args={"pdf_path": str(pdf_path), **args}))
    )


def _make_pdf(tmp_path) -> Path:
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return p


def test_ingest_pdf_attaches_note_when_no_extractor(tmp_path):
    pdf = _make_pdf(tmp_path)
    ingest = _FakeIngest(
        region_extractor=None,
        summary={"slug": "doc", "region_count": 0, "status": "success"},
    )
    out = _call_ingest(ingest, pdf)
    assert out["note"]["gold_skipped"] is True
    assert "ingest_begin" in json.dumps(out["note"])


def test_ingest_pdf_no_note_when_extractor_wired(tmp_path):
    pdf = _make_pdf(tmp_path)
    ingest = _FakeIngest(
        region_extractor=object(),
        summary={"slug": "doc", "region_count": 3, "status": "success"},
    )
    out = _call_ingest(ingest, pdf)
    assert "note" not in out


def test_ingest_pdf_no_note_when_regions_skipped(tmp_path):
    pdf = _make_pdf(tmp_path)
    ingest = _FakeIngest(
        region_extractor=None,
        summary={"slug": "doc", "region_count": 0, "status": "success"},
    )
    out = _call_ingest(ingest, pdf, skip_regions=True)
    assert "note" not in out


def test_ingest_pdf_no_note_when_idempotent_skip(tmp_path):
    pdf = _make_pdf(tmp_path)
    ingest = _FakeIngest(
        region_extractor=None,
        summary={"slug": "doc", "skipped": True, "reason": "already ingested"},
    )
    out = _call_ingest(ingest, pdf)
    assert "note" not in out
