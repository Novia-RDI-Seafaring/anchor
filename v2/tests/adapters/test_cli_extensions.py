"""`anchor extensions` — manifest discovery, registration, removal."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from anchor.adapters.cli.extensions import extensions_app


def _runner():
    return CliRunner()


def test_list_shows_bundled_pdf_producer(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    result = _runner().invoke(extensions_app, ["list", "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 0, result.output
    assert "anchor-pdfs" in result.output
    assert "bundled" in result.output


def test_add_writes_to_system_dir(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "oip_version": "0.1",
        "producer": {"name": "anchor-transcribe", "version": "0.1.0"},
        "data_dir": "/tmp/transcripts",
        "produces": {"source_kinds": ["audio/mp3"], "region_kinds": ["segment"], "source_ref_kinds": ["audio-timestamp"]},
        "invocation": {"kind": "mcp-stdio", "command": "anchor-transcribe-mcp", "tools_namespace": "transcribe"},
    }))
    result = _runner().invoke(extensions_app, ["add", str(manifest)])
    assert result.exit_code == 0, result.output
    assert (home / ".config" / "oip" / "producers.d" / "anchor-transcribe.json").exists()


def test_add_with_project_scope_writes_into_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    data = tmp_path / "anchor-data"
    data.mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "oip_version": "0.1",
        "producer": {"name": "code-regions", "version": "0.1.0"},
        "data_dir": "/tmp/code",
        "produces": {"source_kinds": ["text/x-python"], "region_kinds": ["function"], "source_ref_kinds": ["code-line-range"]},
        "invocation": {"kind": "mcp-stdio", "command": "code-regions-mcp", "tools_namespace": "code"},
    }))
    result = _runner().invoke(extensions_app, [
        "add", str(manifest), "--scope", "project", "--data-dir", str(data)
    ])
    assert result.exit_code == 0, result.output
    assert (data / ".oip" / "producers.d" / "code-regions.json").exists()


def test_add_refuses_invalid_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))

    manifest = tmp_path / "bogus.json"
    manifest.write_text('{"not": "a manifest"}')
    result = _runner().invoke(extensions_app, ["add", str(manifest)])
    assert result.exit_code != 0
    assert "missing oip_version" in result.output or "failed validation" in result.output


def test_add_dedupes_by_default(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))

    manifest = tmp_path / "manifest.json"
    payload = {
        "oip_version": "0.1",
        "producer": {"name": "anchor-transcribe", "version": "0.1.0"},
        "data_dir": "/tmp/transcripts",
        "produces": {"source_kinds": [], "region_kinds": [], "source_ref_kinds": []},
        "invocation": {"kind": "mcp-stdio", "command": "x", "tools_namespace": "x"},
    }
    manifest.write_text(json.dumps(payload))
    runner = _runner()
    runner.invoke(extensions_app, ["add", str(manifest)])
    second = runner.invoke(extensions_app, ["add", str(manifest)])
    assert second.exit_code != 0
    assert "already registered" in second.output
    # --force overrides
    forced = runner.invoke(extensions_app, ["add", str(manifest), "--force"])
    assert forced.exit_code == 0


def test_remove(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))

    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "oip_version": "0.1",
        "producer": {"name": "x", "version": "0.1.0"},
        "data_dir": "/tmp/x",
        "produces": {"source_kinds": [], "region_kinds": [], "source_ref_kinds": []},
        "invocation": {"kind": "mcp-stdio", "command": "x", "tools_namespace": "x"},
    }))
    runner = _runner()
    runner.invoke(extensions_app, ["add", str(manifest)])
    result = runner.invoke(extensions_app, ["remove", "x"])
    assert result.exit_code == 0, result.output
    assert "removed" in result.output


def test_discover_prints_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    result = _runner().invoke(extensions_app, ["discover", "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 0
    assert "system" in result.output
    assert "project" in result.output
    assert "OIP" in result.output


def test_schema_emits_valid_oip(tmp_path):
    result = _runner().invoke(extensions_app, ["schema"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["oip_version"] == "0.1"
    assert "producer" in payload
    assert "invocation" in payload


def test_info_returns_bundled_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    result = _runner().invoke(extensions_app, ["info", "anchor-pdfs", "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["producer"]["name"] == "anchor-pdfs"
    assert payload["invocation"]["tools_namespace"] == "pdf"


def test_info_unknown_returns_error(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))
    result = _runner().invoke(extensions_app, ["info", "no-such-thing"])
    assert result.exit_code != 0
