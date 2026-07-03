"""`anchor serve` falls through to the next free port when one is taken."""
from __future__ import annotations

import socket

from anchor.adapters.cli import serve as serve_mod
from anchor.adapters.cli.serve import _find_free_port


def test_returns_a_bindable_port():
    # Grab an OS-assigned free port, release it, and confirm we can get one.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        start = s.getsockname()[1]
    chosen = _find_free_port("127.0.0.1", start)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", chosen))  # bindable -> no error


def test_skips_a_port_in_use():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        busy = taken.getsockname()[1]
        chosen = _find_free_port("127.0.0.1", busy)
        assert chosen > busy  # didn't pick the in-use port


def test_serve_builds_http_app_from_project_runtime(monkeypatch, tmp_path):
    from anchor.infra import environment as env_mod

    for var in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_CONFIG", "ANCHOR_DATA_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANCHOR_EMBED_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("ANCHOR_OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")

    captured = {}

    def fake_run(app, host, port):
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)

    data_dir = tmp_path / "project-data"
    serve_mod.serve(data_dir=data_dir, host="127.0.0.1", port=0)

    app = captured["app"]
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 0
    assert app.state.anchor_config.data_dir == data_dir
    assert app.state.workspace_service is not None
    assert app.state.ingest_service is not None
    assert app.state.doc_store is not None
    assert app.state.bus is not None
    assert app.state.intent_service is not None
    assert app.state.ingest_session_service is not None
    assert app.state.cad_service is not None
    assert app.state.sysml_service is not None
    assert app.state.synopsis_service is not None
