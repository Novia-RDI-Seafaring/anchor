"""Docling device resolution + CPU fallback (no real docling/torch needed)."""
from __future__ import annotations

import pytest

from anchor.extensions.anchor_pdfs.infra.pdf import docling_extractor as dx


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
    monkeypatch.setattr(dx, "_convert", lambda p, d: seen.setdefault("device", d) or {"items": []})
    dx._extract_sync("x.pdf", device="cpu")
    assert seen["device"] == "cpu"


def test_auto_prefers_gpu_then_falls_back_to_cpu(monkeypatch):
    monkeypatch.setattr(dx, "_resolve_device", lambda req: "mps" if req == "auto" else req)
    calls = []

    def fake_convert(path, device):
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
    monkeypatch.setattr(dx, "_convert", lambda p, d: calls.append(d) or {"items": []})
    dx._extract_sync("x.pdf", device="auto")
    assert calls == ["cpu"]              # straight to CPU, no wasted GPU attempt


def test_non_accelerator_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(dx, "_resolve_device", lambda req: "cuda")
    calls = []

    def fake_convert(path, device):
        calls.append(device)
        raise ValueError("corrupt PDF: bad xref")

    monkeypatch.setattr(dx, "_convert", fake_convert)
    with pytest.raises(ValueError):
        dx._extract_sync("x.pdf", device="auto")
    assert calls == ["cuda"]            # no pointless CPU retry for content errors
