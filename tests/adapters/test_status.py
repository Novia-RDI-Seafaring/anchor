from __future__ import annotations

import pytest

from anchor.infra.config import AnchorConfig
from anchor.adapters.status import build_status_summary
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
    assert "cwd" in status["process"]
