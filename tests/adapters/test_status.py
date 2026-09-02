from __future__ import annotations

import pytest

from anchor.adapters.status import build_status_summary
from anchor.infra.config import AnchorConfig
from tests.fixtures.services import make_in_memory_services


@pytest.mark.asyncio
async def test_status_summary_reports_project_and_counts(tmp_path, monkeypatch):
    monkeypatch.delenv("ANCHOR_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    services = make_in_memory_services()
    await services.workspace.create_workspace("w1")
    services.doc_store.seed_document("pump", filename="pump.pdf", page_count=4)
    await services.doc_store.write_embeddings(
        "pump",
        {
            "embed_model": "test",
            "dim": 2,
            "vectors": [{"page": 1, "region_id": "r1", "text": "x", "vector": [0.0, 1.0]}],
        },
    )

    config = AnchorConfig(data_dir=tmp_path / "anchor-data", openai_api_key=None)
    status = await build_status_summary(
        config=config,
        workspace=services.workspace,
        doc_store=services.doc_store,
    )

    assert status["data_dir"]["path"] == str(tmp_path / "anchor-data")
    assert status["counts"] == {
        "workspaces": 1,
        "documents": 1,
        "embeddings": 1,
    }
    assert status["errors"] == {
        "workspaces": None,
        "documents": None,
        "embeddings": None,
    }
    assert status["api_keys"] == {
        "anchor_openai_api_key": False,
        "openai_api_key": False,
    }
    assert status["provider"]["server_model_egress_allowed"] is False
    assert status["provider"]["server_model_egress_enabled"] is False
    assert status["provider"]["credential_source"] is None
    assert status["provider"]["openai_base_url"] is None
    assert "cwd" in status["process"]


@pytest.mark.asyncio
async def test_status_summary_reports_effective_public_egress(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-public-key")
    services = make_in_memory_services()
    config = AnchorConfig(
        data_dir=tmp_path / "anchor-data",
        provider="openai",
        _env_file=None,
    )

    status = await build_status_summary(
        config=config,
        workspace=services.workspace,
        doc_store=services.doc_store,
    )

    assert status["provider"]["server_model_egress_allowed"] is True
    assert status["provider"]["server_model_egress_enabled"] is True
    assert status["provider"]["credential_source"] == "openai"
    assert status["provider"]["openai_base_url"] == "api.openai.com"


@pytest.mark.asyncio
async def test_status_summary_reports_allowed_but_unconfigured_egress(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    services = make_in_memory_services()
    config = AnchorConfig(
        data_dir=tmp_path / "anchor-data",
        provider="custom",
        openai_base_url="https://models.example/v1",
        embed_model="text-embedding-3-small",
        _env_file=None,
    )

    status = await build_status_summary(
        config=config,
        workspace=services.workspace,
        doc_store=services.doc_store,
    )

    assert status["provider"]["server_model_egress_allowed"] is True
    assert status["provider"]["server_model_egress_enabled"] is False
    assert status["provider"]["openai_base_url"] == "https://models.example/v1"
