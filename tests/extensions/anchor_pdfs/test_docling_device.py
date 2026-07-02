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
    def __init__(self, l, t, r, b):
        self.l = l
        self.t = t
        self.r = r
        self.b = b

    def to_bottom_left_origin(self, page_height):
        return _Box(self.l, page_height - self.t, self.r, page_height - self.b)


def test_flatten_preserves_table_cell_bbox_as_bottom_left():
    doc = SimpleNamespace(
        texts=[],
        pictures=[],
        pages={1: SimpleNamespace(size=SimpleNamespace(height=100))},
        tables=[
            SimpleNamespace(
                prov=[SimpleNamespace(page_no=1, bbox=_Box(0, 90, 80, 10))],
                data=SimpleNamespace(table_cells=[
                    SimpleNamespace(
                        start_row_offset_idx=1,
                        start_col_offset_idx=1,
                        text="cell value",
                        bbox=_Box(10, 20, 30, 40),
                    ),
                ]),
            ),
        ],
    )

    out = dx._flatten(doc)

    assert out["tables"][0]["cells"][0] == {
        "row": 1,
        "col": 1,
        "text": "cell value",
        "bbox": [10.0, 80.0, 30.0, 60.0],
    }
