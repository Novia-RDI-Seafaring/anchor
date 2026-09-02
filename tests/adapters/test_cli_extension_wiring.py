from __future__ import annotations

from types import SimpleNamespace

from anchor.adapters.cli import cad, fmu, sysml
from anchor.adapters.extension_host import ExtensionHost


def test_cad_and_fmu_cli_build_through_extension_host(tmp_path, monkeypatch):
    services = {"cad": object(), "fmu": object()}
    calls: list[tuple[str, object, object | None]] = []

    def start(self, name, *, bus, workspace=None):
        assert self.data_dir == tmp_path
        calls.append((name, bus, workspace))
        return services[name]

    monkeypatch.setattr(ExtensionHost, "start", start)

    assert cad._build_cad_service(tmp_path) is services["cad"]
    assert fmu._build_fmu_service(tmp_path) is services["fmu"]
    assert [call[0] for call in calls] == ["cad", "fmu"]
    assert all(call[2] is None for call in calls)


def test_sysml_cli_passes_canvas_runtime_to_extension_host(tmp_path, monkeypatch):
    service = object()
    expected_bus = object()
    expected_workspace = object()
    monkeypatch.setattr(
        sysml,
        "_build_canvas_runtime",
        lambda _data_dir: SimpleNamespace(
            bus=expected_bus,
            workspace=expected_workspace,
        ),
    )

    def start(self, name, *, bus, workspace=None):
        assert self.data_dir == tmp_path
        assert name == "sysml"
        assert bus is expected_bus
        assert workspace is expected_workspace
        return service

    monkeypatch.setattr(ExtensionHost, "start", start)

    assert sysml._build_sysml_service(tmp_path) is service
