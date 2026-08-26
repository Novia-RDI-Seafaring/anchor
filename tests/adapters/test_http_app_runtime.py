from __future__ import annotations

from fastapi.testclient import TestClient

from anchor.adapters.extension_host import ExtensionRuntimeStatus
from anchor.adapters.http.app import build_app
from anchor.adapters.project_runtime import ProjectRuntime, RuntimeProfile
from anchor.infra.config import AnchorConfig
from tests.fixtures.services import make_in_memory_services


def test_build_app_accepts_project_runtime(tmp_path):
    services = make_in_memory_services()
    config = AnchorConfig(data_dir=tmp_path / "anchor-data", _env_file=None)
    runtime = ProjectRuntime(
        profile=RuntimeProfile.FULL,
        config=config,
        bus=services.bus,
        workspace=services.workspace,
        ingest=services.ingest,
        doc_store=services.doc_store,
        intents=services.intents,
        ingest_session=services.ingest_session,
        extension_status={
            "anchor-fmus": ExtensionRuntimeStatus(
                name="anchor-fmus",
                source="bundled",
                available=False,
                reason="missing runtime",
                error_type="RuntimeError",
            )
        },
    )

    app = build_app(runtime)

    assert app.state.anchor_config is config
    assert app.state.workspace_service is services.workspace
    assert app.state.ingest_service is services.ingest
    assert app.state.doc_store is services.doc_store
    assert app.state.bus is services.bus
    assert app.state.intent_service is services.intents
    assert app.state.ingest_session_service is services.ingest_session
    assert app.state.tailer_registry is not None

    response = TestClient(app).get("/api/extensions/status")
    assert response.status_code == 200
    assert response.json()["summary"] == {"available": 0, "unavailable": 1}
