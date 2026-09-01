"""Docling device resolution + CPU fallback (no real docling/torch needed)."""
from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

from anchor.extensions.anchor_pdfs.infra.pdf import docling_extractor as dx


@pytest.fixture(autouse=True)
def _stub_ocr_backend(monkeypatch):
    """Never import the real onnxruntime (issue #195 numpy double-load).

    These tests drive ``_extract_sync``, which calls ``_assert_ocr_backend``
    and imports ``onnxruntime``. Importing the real wheel here is the source of
    the flaky 'cannot load module more than once per process' failure, so we
    patch the import boundary to make the backend deterministically present.
    """
    real_import = importlib.import_module
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name, *a, **k: object() if name == "onnxruntime" else real_import(name, *a, **k),
    )


@pytest.fixture(autouse=True)
def _clear_fallback():
    dx._FELL_BACK.clear()
    yield
    dx._FELL_BACK.clear()


def test_auto_never_selects_mps():
    # docling's layout model needs float64 (MPS can't), so auto must avoid mps
    # even on a Mac where torch exposes it.
    assert dx._resolve_device("auto") in ("cuda", "cpu")


def test_explicit_mps_is_passed_through():
    assert dx._resolve_device("mps") == "mps"


def test_explicit_device_is_passed_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(dx, "_convert", lambda p, d, f=False: seen.setdefault("device", d) or {"items": []})
    dx._extract_sync("x.pdf", device="cpu")
    assert seen["device"] == "cpu"


def test_full_page_ocr_threads_through_to_convert(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        dx,
        "_convert",
        lambda p, d, f=False: seen.setdefault("full_page_ocr", f) or {"items": []},
    )
    dx._extract_sync("x.pdf", device="cpu", full_page_ocr=True)
    assert seen["full_page_ocr"] is True


def test_auto_prefers_gpu_then_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(dx, "_resolve_device", lambda req: "mps" if req == "auto" else req)
    calls = []

    def fake_convert(path, device, full_page_ocr=False):
        calls.append(device)
        if device != "cpu":
            raise RuntimeError("Cannot convert a MPS Tensor to float64 ...")
        return {"items": [], "tables": []}

    monkeypatch.setattr(dx, "_convert", fake_convert)
    out = dx._extract_sync("x.pdf", device="auto")
    assert calls == ["mps", "cpu"]      # tried GPU, then recovered on CPU
    assert out == {"items": [], "tables": []}
    assert "mps" in dx._FELL_BACK        # remembered so the next doc skips it


def test_second_doc_skips_known_bad_device(monkeypatch):
    dx._FELL_BACK.add("mps")
    monkeypatch.setattr(dx, "_resolve_device", lambda req: "mps")
    calls = []
    monkeypatch.setattr(dx, "_convert", lambda p, d, f=False: calls.append(d) or {"items": []})
    dx._extract_sync("x.pdf", device="auto")
    assert calls == ["cpu"]              # straight to CPU, no wasted GPU attempt


def test_non_accelerator_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(dx, "_resolve_device", lambda req: "cuda")
    calls = []

    def fake_convert(path, device, full_page_ocr=False):
        calls.append(device)
        raise ValueError("corrupt PDF: bad xref")

    monkeypatch.setattr(dx, "_convert", fake_convert)
    with pytest.raises(ValueError):
        dx._extract_sync("x.pdf", device="auto")
    assert calls == ["cuda"]            # no pointless CPU retry for content errors


class _Box:
    """Models docling's BoundingBox: an explicit coord_origin plus converters.

    Docling provenance boxes are BOTTOMLEFT (PDF user space) by default; table
    cell boxes are TOPLEFT. `_flatten` must convert both to Anchor's canonical
    top-left convention (#281) using the page height."""

    def __init__(self, left, top, right, bottom, origin="BOTTOMLEFT"):
        self.l = left
        self.t = top
        self.r = right
        self.b = bottom
        self.coord_origin = origin

    def to_bottom_left_origin(self, page_height):
        if self.coord_origin == "BOTTOMLEFT":
            return self
        return _Box(self.l, page_height - self.t, self.r, page_height - self.b, "BOTTOMLEFT")

    def to_top_left_origin(self, page_height):
        if self.coord_origin == "TOPLEFT":
            return self
        return _Box(self.l, page_height - self.t, self.r, page_height - self.b, "TOPLEFT")


def test_flatten_emits_top_left_boxes_page_sizes_and_origin_stamp():
    doc = SimpleNamespace(
        texts=[],
        pictures=[],
        pages={1: SimpleNamespace(size=SimpleNamespace(width=80, height=100))},
        tables=[
            SimpleNamespace(
                # BOTTOMLEFT provenance: top y=90 is near the page top.
                prov=[SimpleNamespace(page_no=1, bbox=_Box(0, 90, 80, 10))],
                data=SimpleNamespace(table_cells=[
                    SimpleNamespace(
                        start_row_offset_idx=1,
                        start_col_offset_idx=1,
                        text="cell value",
                        # Cell boxes are already TOPLEFT in docling.
                        bbox=_Box(10, 20, 30, 40, "TOPLEFT"),
                    ),
                ]),
            ),
        ],
    )

    out = dx._flatten(doc)

    assert out["coord_origin"] == "top-left"
    assert out["pages"] == {1: {"width": 80.0, "height": 100.0}}
    # Table bbox flipped into top-left: y' = 100 - y.
    assert out["tables"][0]["bbox"] == [0.0, 10.0, 80.0, 90.0]
    assert out["tables"][0]["cells"][0] == {
        "row": 1,
        "col": 1,
        "text": "cell value",
        "bbox": [10.0, 20.0, 30.0, 40.0],
    }


def test_flatten_keeps_each_text_provenance_bbox():
    doc = SimpleNamespace(
        texts=[
            SimpleNamespace(
                label="text",
                text="left right",
                prov=[
                    SimpleNamespace(page_no=1, bbox=_Box(10, 90, 80, 80), charspan=(0, 4)),
                    SimpleNamespace(page_no=1, bbox=_Box(300, 500, 550, 300), charspan=(5, 10)),
                ],
            ),
        ],
        pictures=[],
        pages={1: SimpleNamespace(size=SimpleNamespace(width=600, height=1000))},
        tables=[],
    )

    out = dx._flatten(doc)

    assert [item["text"] for item in out["items"]] == ["left", "right"]
    # Each provenance box is converted from BOTTOMLEFT to top-left (y' = 1000 - y)
    # and normalised to top <= bottom.
    assert [item["bbox"] for item in out["items"]] == [
        [10.0, 910.0, 80.0, 920.0],
        [300.0, 500.0, 550.0, 700.0],
    ]


def test_flatten_fails_closed_without_a_page_height():
    # A BOTTOMLEFT box cannot be converted without the page height; emit []
    # rather than a silently mis-oriented bbox.
    doc = SimpleNamespace(
        texts=[SimpleNamespace(label="text", text="x", prov=[
            SimpleNamespace(page_no=1, bbox=_Box(10, 90, 80, 80), charspan=(0, 1)),
        ])],
        pictures=[], pages={}, tables=[],
    )
    assert dx._flatten(doc)["items"][0]["bbox"] == []
