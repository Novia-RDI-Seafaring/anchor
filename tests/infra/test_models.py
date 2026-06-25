"""Offline-model provisioning + no-egress env enforcement (infra.models)."""
from __future__ import annotations

from anchor.infra.models import (
    DEFAULT_EMBED_MODEL,
    HF_OFFLINE_VARS,
    enforce_offline,
    offline_active,
    prefetch_models,
    required_models,
)


def _clear_offline(monkeypatch):
    for var in HF_OFFLINE_VARS:
        monkeypatch.delenv(var, raising=False)


def test_required_models_includes_local_embedder_and_docling():
    specs = required_models(DEFAULT_EMBED_MODEL)
    kinds = {s.kind for s in specs}
    assert kinds == {"embed", "docling"}
    assert any(s.repo_id == DEFAULT_EMBED_MODEL for s in specs)


def test_required_models_skips_remote_embedder():
    # A text-embedding-* model never loads local weights, so prefetch only needs docling.
    specs = required_models("text-embedding-3-small")
    assert [s.kind for s in specs] == ["docling"]


def test_enforce_offline_sets_both_vars(monkeypatch):
    _clear_offline(monkeypatch)
    assert offline_active() is False
    newly = enforce_offline()
    assert set(newly) == set(HF_OFFLINE_VARS)
    assert offline_active() is True


def test_enforce_offline_respects_operator_value(monkeypatch):
    # An operator who deliberately disabled offline (for a prefetch) is honored.
    _clear_offline(monkeypatch)
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    newly = enforce_offline()
    # Only the unset var is touched; the explicit 0 is left alone.
    assert "HF_HUB_OFFLINE" not in newly
    assert "TRANSFORMERS_OFFLINE" in newly
    import os

    assert os.environ["HF_HUB_OFFLINE"] == "0"


def test_prefetch_loads_each_model_and_reports(monkeypatch):
    loaded: list[str] = []
    monkeypatch.setattr("anchor.infra.models._warm_embedder",lambda repo: loaded.append(f"embed:{repo}"))
    monkeypatch.setattr("anchor.infra.models._warm_docling",lambda: loaded.append("docling"))

    results = prefetch_models(DEFAULT_EMBED_MODEL)

    assert loaded == [f"embed:{DEFAULT_EMBED_MODEL}", "docling"]
    assert all(r["ok"] for r in results)
    assert {r["kind"] for r in results} == {"embed", "docling"}


def test_prefetch_reports_failure_without_aborting(monkeypatch):
    def boom() -> None:
        raise RuntimeError("hub unreachable")

    monkeypatch.setattr("anchor.infra.models._warm_embedder",lambda repo: None)
    monkeypatch.setattr("anchor.infra.models._warm_docling",boom)

    results = prefetch_models(DEFAULT_EMBED_MODEL)

    by_kind = {r["kind"]: r for r in results}
    assert by_kind["embed"]["ok"] is True
    assert by_kind["docling"]["ok"] is False
    assert "hub unreachable" in by_kind["docling"]["detail"]
