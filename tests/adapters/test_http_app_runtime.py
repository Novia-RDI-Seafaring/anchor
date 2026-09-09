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


def test_extension_status_route_lists_discovered_producers(tmp_path, monkeypatch):
    """#308 parity: HTTP serves the same producers section as CLI/MCP."""
    import json

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    services = make_in_memory_services()
    data_dir = tmp_path / "anchor-data"
    project_dir = data_dir / ".oip" / "producers.d"
    project_dir.mkdir(parents=True)
    (project_dir / "tracer.json").write_text(json.dumps({
        "oip_version": "0.1",
        "producer": {"name": "tracer", "version": "1.0.0"},
        "invocation": {"kind": "mcp-stdio", "command": "no-such-binary-xyz"},
    }))
    config = AnchorConfig(data_dir=data_dir, _env_file=None)
    runtime = ProjectRuntime(
        profile=RuntimeProfile.FULL,
        config=config,
        bus=services.bus,
        workspace=services.workspace,
        ingest=services.ingest,
        doc_store=services.doc_store,
        intents=services.intents,
        ingest_session=services.ingest_session,
    )

    response = TestClient(build_app(runtime)).get("/api/extensions/status")

    assert response.status_code == 200
    producers = response.json()["producers"]
    assert "never started by Anchor" in producers["note"]
    items = {item["name"]: item for item in producers["items"]}
    assert items["tracer"]["source"] == "project"
    assert items["tracer"]["command_found"] is False
    assert items["tracer"]["check"] == "command not found on PATH"
    assert items["tracer"]["started"] is False
