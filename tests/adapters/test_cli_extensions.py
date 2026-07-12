"""`anchor extensions` — manifest discovery, registration, removal."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult, TextContent, Tool
from typer.testing import CliRunner

from anchor.adapters.cli import extensions as extensions_module
from anchor.adapters.cli.extensions import extensions_app
from anchor.adapters.extension_host import ExtensionRuntimeStatus
from anchor.adapters.external_oip.gateway import (
    ExternalProducerStatus,
    GatewayCatalog,
)


def _runner():
    return CliRunner()


def test_list_shows_bundled_pdf_producer(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    result = _runner().invoke(extensions_app, ["list", "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 0, result.output
    assert "anchor-pdfs" in result.output
    assert "anchor-sysml" in result.output
    assert "experimental" in result.output
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
    assert not (
        home / ".config" / "oip" / "producers.d" / "anchor-transcribe.enabled"
    ).exists()
    assert "execution disabled" in result.output


def test_add_enable_and_disable_manage_execution_marker(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "oip_version": "0.1",
        "producer": {"name": "enabled-producer", "version": "1.0.0"},
        "invocation": {
            "kind": "mcp-stdio",
            "command": "producer-mcp",
            "tools_namespace": "enabled",
        },
    }), encoding="utf-8")
    runner = _runner()

    added = runner.invoke(extensions_app, ["add", str(manifest), "--enable"])
    marker = config_home / "oip" / "producers.d" / "enabled-producer.enabled"
    assert added.exit_code == 0, added.output
    assert marker.read_text(encoding="utf-8") == "enabled\n"

    disabled = runner.invoke(extensions_app, ["disable", "enabled-producer"])
    assert disabled.exit_code == 0, disabled.output
    assert not marker.exists()

    enabled = runner.invoke(extensions_app, ["enable", "enabled-producer"])
    assert enabled.exit_code == 0, enabled.output
    assert marker.is_file()


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


def test_add_refuses_producer_name_path_traversal(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "oip_version": "0.1",
            "producer": {"name": "../../outside", "version": "0.1.0"},
        }),
        encoding="utf-8",
    )

    result = _runner().invoke(extensions_app, ["add", str(manifest)])

    assert result.exit_code != 0
    assert "producer.name" in result.output
    assert not (config_home / "outside.json").exists()


def test_add_refuses_unknown_registration_scope(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "oip_version": "0.1",
            "producer": {"name": "safe-name", "version": "0.1.0"},
        }),
        encoding="utf-8",
    )

    result = _runner().invoke(
        extensions_app,
        ["add", str(manifest), "--scope", "somewhere"],
    )

    assert result.exit_code != 0
    assert "scope must be 'system' or 'project'" in result.output
    assert not (config_home / "oip" / "producers.d").exists()


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


def test_remove_refuses_producer_name_path_traversal(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    victim = config_home / "victim.json"
    victim.parent.mkdir(parents=True)
    victim.write_text("keep", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    result = _runner().invoke(extensions_app, ["remove", "../../victim"])

    assert result.exit_code != 0
    assert "producer.name" in result.output
    assert victim.read_text(encoding="utf-8") == "keep"


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


def test_status_emits_shared_runtime_diagnostics(tmp_path, monkeypatch):
    from anchor.adapters import project_runtime

    runtime = SimpleNamespace(extension_status={
        "anchor-fmus": ExtensionRuntimeStatus(
            name="anchor-fmus",
            source="bundled",
            available=False,
            reason="FMPy missing",
            error_type="RuntimeError",
        ),
    })
    monkeypatch.setattr(
        project_runtime,
        "build_project_runtime_for_data_dir",
        lambda *_args, **_kwargs: runtime,
    )

    async def external_catalog(_data_dir):
        return GatewayCatalog(tools=(), statuses=())

    monkeypatch.setattr(extensions_module, "_external_catalog", external_catalog)

    result = _runner().invoke(
        extensions_app,
        ["status", "--data-dir", str(tmp_path / "data")],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "extensions": [{
            "name": "anchor-fmus",
            "source": "bundled",
            "available": False,
            "reason": "FMPy missing",
            "error_type": "RuntimeError",
        }],
        "summary": {"available": 0, "unavailable": 1},
    }


class _FakeGateway:
    def __init__(self) -> None:
        self.closed = False

    async def catalog(self):
        return GatewayCatalog(
            tools=(
                Tool(
                    name="vendor.echo",
                    description="Echo externally",
                    inputSchema={"type": "object"},
                ),
            ),
            statuses=(
                ExternalProducerStatus(
                    name="vendor",
                    source="project",
                    available=True,
                    tool_count=1,
                ),
            ),
        )

    async def call(self, name, arguments):
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps({"name": name, "arguments": arguments}),
                )
            ]
        )

    async def close(self):
        self.closed = True


@pytest.fixture
def external_gateway(monkeypatch):
    gateways: list[_FakeGateway] = []

    def build(_data_dir):
        gateway = _FakeGateway()
        gateways.append(gateway)
        return gateway

    monkeypatch.setattr(extensions_module, "build_external_gateway", build)
    return gateways


def test_external_tools_print_namespaced_catalog(tmp_path, external_gateway):
    result = _runner().invoke(
        extensions_app,
        ["tools", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["tools"][0]["name"] == "vendor.echo"
    assert external_gateway[0].closed is True


def test_external_call_forwards_json_object(tmp_path, external_gateway):
    result = _runner().invoke(
        extensions_app,
        [
            "call",
            "vendor.echo",
            "--args",
            '{"value": 9}',
            "--data-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    forwarded = json.loads(payload["content"][0]["text"])
    assert forwarded == {
        "name": "vendor.echo",
        "arguments": {"value": 9},
    }
    assert external_gateway[0].closed is True
