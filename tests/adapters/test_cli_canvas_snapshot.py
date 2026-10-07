"""`anchor canvas snapshot` — base-url resolution via the serve registry (#306).

The command used to hardcode `--base-url http://localhost:8002`; with the
project's serve on another port the headless chromium navigated to the wrong
server and captured an empty grid with no error. It now resolves the base URL
through the serve registry, the same lookup `anchor canvas url` uses.
"""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from anchor.adapters.cli.main import app
from anchor.infra import environment as env_mod
from anchor.infra import serve_registry as sr

runner = CliRunner()


def _isolate(monkeypatch, tmp_path):
    for var in ("ANCHOR_ENV", "ANCHOR_PROJECT", "ANCHOR_HTTP_PORT", "ANCHOR_HTTP_HOST"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(env_mod, "ANCHOR_HOME", tmp_path / ".anchor")
    monkeypatch.setattr(env_mod, "LEGACY_DATA_DIR", tmp_path / "_legacy_unused")


def test_resolve_serve_base_url_prefers_registry(monkeypatch, tmp_path):
    from anchor.adapters.cli.common import resolve_serve_base_url

    _isolate(monkeypatch, tmp_path)
    data_dir = tmp_path / "proj" / ".anchor_data"
    data_dir.mkdir(parents=True)
    path = sr.register_serve(
        host="0.0.0.0", port=8003, data_dir=data_dir, started_at="t"
    )
    try:
        url, found = resolve_serve_base_url(data_dir)
    finally:
        sr.unregister_serve(path)
    # 0.0.0.0 is rewritten to a loopback address that actually resolves.
    assert (url, found) == ("http://127.0.0.1:8003", True)


def test_resolve_serve_base_url_falls_back_to_config(monkeypatch, tmp_path):
    from anchor.adapters.cli.common import resolve_serve_base_url

    _isolate(monkeypatch, tmp_path)
    url, found = resolve_serve_base_url(tmp_path / "nothing-here")
    assert url == "http://127.0.0.1:8002"
    assert found is False


def _capture_runtime(monkeypatch, tmp_path):
    """Stub the canvas runtime; capture the base_url the CLI resolved."""
    from anchor.adapters.cli import canvas_snapshot as snap_mod
    from anchor.core.ports.snapshot import SnapshotResult

    captured: dict = {}

    class _Workspace:
        async def snapshot(self, slug, **kwargs):
            out = tmp_path / "shot.png"
            out.write_bytes(b"\x89PNG")
            return SnapshotResult(format="png", content_type="image/png", path=out)

    class _Runtime:
        workspace = _Workspace()

    def fake_build(data_dir: Path, *, base_url: str):
        captured["base_url"] = base_url
        return _Runtime()

    monkeypatch.setattr(snap_mod, "_build_canvas_runtime", fake_build)
    return captured


def test_snapshot_resolves_base_url_from_serve_registry(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    captured = _capture_runtime(monkeypatch, tmp_path)
    data_dir = tmp_path / "proj" / ".anchor_data"
    data_dir.mkdir(parents=True)
    path = sr.register_serve(
        host="127.0.0.1", port=8014, data_dir=data_dir, started_at="t"
    )
    try:
        result = runner.invoke(
            app, ["canvas", "snapshot", "w1", "--data-dir", str(data_dir)]
        )
    finally:
        sr.unregister_serve(path)
    assert result.exit_code == 0, result.output
    assert captured["base_url"] == "http://127.0.0.1:8014"


def test_snapshot_warns_when_no_serve_bound(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    captured = _capture_runtime(monkeypatch, tmp_path)
    data_dir = tmp_path / "proj" / ".anchor_data"
    data_dir.mkdir(parents=True)
    result = runner.invoke(
        app, ["canvas", "snapshot", "w1", "--data-dir", str(data_dir)]
    )
    assert result.exit_code == 0, result.output
    assert captured["base_url"] == "http://127.0.0.1:8002"
    assert "no `anchor serve` is bound" in result.output


def test_snapshot_explicit_base_url_overrides_registry(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    captured = _capture_runtime(monkeypatch, tmp_path)
    data_dir = tmp_path / "proj" / ".anchor_data"
    data_dir.mkdir(parents=True)
    path = sr.register_serve(
        host="127.0.0.1", port=8014, data_dir=data_dir, started_at="t"
    )
    try:
        result = runner.invoke(
            app,
            [
                "canvas", "snapshot", "w1",
                "--data-dir", str(data_dir),
                "--base-url", "http://localhost:9999",
            ],
        )
    finally:
        sr.unregister_serve(path)
    assert result.exit_code == 0, result.output
    assert captured["base_url"] == "http://localhost:9999"
