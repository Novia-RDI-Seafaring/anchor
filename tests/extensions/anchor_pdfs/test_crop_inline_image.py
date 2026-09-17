"""An agent asking to see a region gets an image, not a file path.

`get_crop` and `get_page_image` exist so an agent can LOOK at a chart or a
page. Returning a filesystem path leaves the agent to open the file itself,
which walks off the adapter surface and, in a sandboxed harness, may not be
permitted at all. These tests pin the inline default and the escape hatches.
"""
from __future__ import annotations

import asyncio
import base64
import json

import pytest

from anchor.extensions.anchor_pdfs.mcp_handlers import _byte_envelope
from anchor.extensions.anchor_pdfs.mcp_tool_definitions import tool_definitions

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001od0a2db40000000049454e44ae426082"
    .replace("od", "0d")
)


@pytest.fixture
def png(tmp_path):
    p = tmp_path / "r1.png"
    p.write_bytes(PNG)
    return p


def test_inline_returns_an_mcp_image_envelope(png):
    out = json.loads(_byte_envelope(png, fmt="inline", fallback_ext=".png"))
    assert out["_mcp_mime"] == "image/png"
    assert base64.b64decode(out["_mcp_image_b64"]) == PNG
    # No stray keys: the server promotes on the marker alone.
    assert set(out) == {"_mcp_image_b64", "_mcp_mime"}


def test_inline_envelope_matches_what_the_server_promotes(png):
    # adapters/mcp/server.py promotes a tool result to ImageContent when the
    # decoded JSON carries a top-level "_mcp_image_b64". Pin that contract
    # from the producing side, using the real envelope.
    from mcp.types import ImageContent

    decoded = json.loads(_byte_envelope(png, fmt="inline", fallback_ext=".png"))
    assert "_mcp_image_b64" in decoded

    block = ImageContent(
        type="image",
        data=decoded["_mcp_image_b64"],
        mimeType=decoded.get("_mcp_mime", "image/png"),
    )
    assert block.type == "image"
    assert base64.b64decode(block.data) == PNG


def test_path_and_base64_still_work(png):
    as_path = json.loads(_byte_envelope(png, fmt="path", fallback_ext=".png"))
    assert as_path == {"format": "path", "value": str(png), "content_type": "image/png"}

    as_b64 = json.loads(_byte_envelope(png, fmt="base64", fallback_ext=".png"))
    assert as_b64["format"] == "base64"
    assert base64.b64decode(as_b64["value"]) == PNG
    assert as_b64["size_bytes"] == len(PNG)


def test_inline_falls_back_to_base64_for_non_images(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    out = json.loads(_byte_envelope(pdf, fmt="inline", fallback_ext=".pdf"))
    assert "_mcp_image_b64" not in out
    assert out["format"] == "base64"
    assert out["content_type"] == "application/pdf"


def test_inline_falls_back_to_base64_for_svg(tmp_path):
    svg = tmp_path / "d.svg"
    svg.write_bytes(b"<svg/>")
    out = json.loads(_byte_envelope(svg, fmt="inline", fallback_ext=".svg"))
    assert "_mcp_image_b64" not in out
    assert out["format"] == "base64"


def test_unknown_format_names_every_option(png):
    out = json.loads(_byte_envelope(png, fmt="nope", fallback_ext=".png"))
    assert "inline" in out["error"] and "path" in out["error"] and "base64" in out["error"]


def test_missing_file_still_reports_not_found():
    assert json.loads(_byte_envelope(None, fmt="inline"))["error"] == "not found"


@pytest.mark.parametrize("tool_name", ["get_crop", "get_page_image"])
def test_viewing_tools_default_to_inline(tool_name):
    tool = next(t for t in tool_definitions() if t["name"] == tool_name)
    fmt = tool["inputSchema"]["properties"]["format"]
    assert fmt["default"] == "inline"
    assert set(fmt["enum"]) == {"inline", "path", "base64"}


def test_get_pdf_is_not_an_image_tool_and_keeps_its_path_default():
    tool = next(t for t in tool_definitions() if t["name"] == "get_pdf")
    assert tool["inputSchema"]["properties"]["format"]["default"] == "path"


def test_get_crop_returns_an_inline_image_through_the_handler(tmp_path):
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool
    from tests.fixtures.services import make_in_memory_services

    services = make_in_memory_services()
    store = FsDocStore(tmp_path)

    async def run():
        # Seed a rendered crop at the canonical gold path so the lazy
        # renderer has nothing to do and the handler just serves it.
        await store.write_crop("demo", "4/r1.png", PNG)
        return json.loads(
            await call_tool(
                services.ingest, store, "get_crop", {"slug": "demo", "rel_path": "4/r1.png"}
            )
        )

    out = asyncio.run(run())
    assert out.get("_mcp_mime") == "image/png", out
    assert base64.b64decode(out["_mcp_image_b64"]) == PNG


def test_get_crop_path_format_still_returns_a_path(tmp_path):
    from anchor.extensions.anchor_pdfs.infra.fs_doc_store import FsDocStore
    from anchor.extensions.anchor_pdfs.mcp_handlers import call_tool
    from tests.fixtures.services import make_in_memory_services

    services = make_in_memory_services()
    store = FsDocStore(tmp_path)

    async def run():
        await store.write_crop("demo", "4/r1.png", PNG)
        return json.loads(
            await call_tool(
                services.ingest,
                store,
                "get_crop",
                {"slug": "demo", "rel_path": "4/r1.png", "format": "path"},
            )
        )

    out = asyncio.run(run())
    assert out["format"] == "path"
    assert out["value"].endswith("4/r1.png")


def test_ingest_get_page_downgrades_inline_because_it_nests_the_envelope(tmp_path):
    # The marker is only promoted at the top level of a tool result. Nested
    # under "image" it would be an unviewable blob, so inline must degrade to
    # base64 rather than hand back a broken promise.
    from anchor.extensions.anchor_pdfs.mcp_handlers import _call_session_tool

    class FakeSession:
        async def ingest_get_page(self, session_id, page):
            img = tmp_path / "p1.png"
            img.write_bytes(PNG)
            return {"page": page, "image_path": str(img), "raw_md": "x"}

    out = json.loads(
        asyncio.run(
            _call_session_tool(
                FakeSession(),
                "ingest_get_page",
                {"session_id": "s", "page": 1, "format": "inline"},
            )
        )
    )
    assert "_mcp_image_b64" not in out
    assert out["image"]["format"] == "base64"
    assert base64.b64decode(out["image"]["value"]) == PNG
