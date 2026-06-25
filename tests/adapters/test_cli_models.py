"""`anchor models` — list + prefetch the local model set for offline ingests."""
from __future__ import annotations

import json

from typer.testing import CliRunner

import anchor.infra.models as models_mod
from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod

runner = CliRunner()


def _isolate(monkeypatch, tmp_path):
    for name in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_OPENAI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def test_models_list_reports_required_set(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    result = runner.invoke(app, ["models", "list"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["embed_model"] == "BAAI/bge-small-en-v1.5"
    kinds = {m["kind"] for m in payload["models"]}
    assert kinds == {"embed", "docling"}


def test_models_prefetch_invokes_warmers_and_succeeds(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(models_mod, "_warm_embedder", lambda repo: None)
    monkeypatch.setattr(models_mod, "_warm_docling", lambda: None)

    result = runner.invoke(app, ["models", "prefetch"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert all(r["ok"] for r in payload["prefetched"])


def test_models_prefetch_exits_nonzero_on_failure(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)

    def boom() -> None:
        raise RuntimeError("offline, cannot fetch")

    monkeypatch.setattr(models_mod, "_warm_embedder", lambda repo: None)
    monkeypatch.setattr(models_mod, "_warm_docling", boom)

    result = runner.invoke(app, ["models", "prefetch"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert any(not r["ok"] for r in payload["prefetched"])


def test_models_prefetch_honors_embed_model_override(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    seen: list[str] = []
    monkeypatch.setattr(models_mod, "_warm_embedder", lambda repo: seen.append(repo))
    monkeypatch.setattr(models_mod, "_warm_docling", lambda: None)

    result = runner.invoke(
        app, ["models", "prefetch", "--embed-model", "BAAI/bge-small-en-v1.5"]
    )

    assert result.exit_code == 0, result.output
    assert seen == ["BAAI/bge-small-en-v1.5"]
