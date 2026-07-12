from __future__ import annotations

import json

import pytest

from anchor.adapters.extension_host import (
    ExtensionHost,
    ExtensionRuntimeStatus,
    bundled_manifests,
    discover_manifests,
    discover_third_party_manifest_paths,
    extension_runtime_status_payload,
    load_manifest,
    project_producers_dir,
    registration_dir,
    registration_path,
    system_producers_dir,
)


def _manifest(name: str) -> dict[str, object]:
    return {
        "oip_version": "0.1",
        "producer": {"name": name, "version": "0.1.0"},
        "produces": {
            "source_kinds": [],
            "region_kinds": [],
            "source_ref_kinds": [],
        },
        "invocation": {
            "kind": "mcp-stdio",
            "command": "noop",
            "tools_namespace": name,
        },
    }


def test_bundled_manifests_match_current_public_discovery():
    names = [m["producer"]["name"] for m in bundled_manifests()]
    assert names == ["anchor-pdfs", "anchor-fmus", "anchor-cad", "anchor-sysml"]
    sysml = bundled_manifests()[-1]
    assert sysml["maturity"] == "experimental"


def test_extension_host_starts_bundled_runtimes(tmp_path, monkeypatch):
    from anchor.extensions.anchor_cad import extension as cad_ext
    from anchor.extensions.anchor_fmus import extension as fmu_ext
    from anchor.extensions.anchor_sysml import extension as sysml_ext

    cad_service = object()
    fmu_service = object()
    sysml_service = object()
    calls: list[tuple[str, object, object, object | None]] = []

    def build_cad(data_dir, bus):
        calls.append(("cad", data_dir, bus, None))
        return cad_service

    def build_fmu(data_dir, bus):
        calls.append(("fmu", data_dir, bus, None))
        return fmu_service

    def build_sysml(data_dir, bus, *, workspace):
        calls.append(("sysml", data_dir, bus, workspace))
        return sysml_service

    monkeypatch.setattr(cad_ext, "build_service", build_cad)
    monkeypatch.setattr(fmu_ext, "build_service", build_fmu)
    monkeypatch.setattr(sysml_ext, "build_service", build_sysml)
    bus = object()
    workspace = object()

    runtimes = ExtensionHost(tmp_path).start_bundled(
        bus=bus,  # type: ignore[arg-type]
        workspace=workspace,  # type: ignore[arg-type]
    )

    assert runtimes.cad is cad_service
    assert runtimes.fmu is fmu_service
    assert runtimes.sysml is sysml_service
    assert calls == [
        ("cad", tmp_path, bus, None),
        ("fmu", tmp_path, bus, None),
        ("sysml", tmp_path, bus, workspace),
    ]
    assert set(runtimes.status) == {"anchor-cad", "anchor-fmus", "anchor-sysml"}
    assert all(item.available for item in runtimes.status.values())


def test_extension_host_requires_data_dir_for_runtime_startup():
    with pytest.raises(RuntimeError, match="requires a project data_dir"):
        ExtensionHost().start_bundled(
            bus=object(),  # type: ignore[arg-type]
            workspace=object(),  # type: ignore[arg-type]
        )


def test_extension_host_rejects_unknown_runtime_name(tmp_path):
    with pytest.raises(ValueError, match="unknown bundled runtime"):
        ExtensionHost(tmp_path).start(
            "unknown",  # type: ignore[arg-type]
            bus=object(),  # type: ignore[arg-type]
        )


def test_extension_runtime_status_payload_is_stable_and_adapter_neutral():
    payload = extension_runtime_status_payload({
        "anchor-fmus": ExtensionRuntimeStatus(
            name="anchor-fmus",
            source="bundled",
            available=False,
            reason="missing runtime",
            error_type="RuntimeError",
        ),
        "anchor-cad": ExtensionRuntimeStatus(
            name="anchor-cad",
            source="bundled",
            available=True,
        ),
    })

    assert payload == {
        "extensions": [
            {
                "name": "anchor-cad",
                "source": "bundled",
                "available": True,
                "reason": None,
                "error_type": None,
            },
            {
                "name": "anchor-fmus",
                "source": "bundled",
                "available": False,
                "reason": "missing runtime",
                "error_type": "RuntimeError",
            },
        ],
        "summary": {"available": 1, "unavailable": 1},
    }


def test_discover_manifests_groups_bundled_system_and_project(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    system_dir = config_home / "oip" / "producers.d"
    project_dir = project_producers_dir(tmp_path / "anchor-data")
    system_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    (system_dir / "system.json").write_text(
        json.dumps(_manifest("system-producer")),
        encoding="utf-8",
    )
    (project_dir / "project.json").write_text(
        json.dumps(_manifest("project-producer")),
        encoding="utf-8",
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    groups = discover_manifests(tmp_path / "anchor-data")

    assert [m["producer"]["name"] for m in groups["system"]] == ["system-producer"]
    assert [m["producer"]["name"] for m in groups["project"]] == ["project-producer"]
    assert [m["producer"]["name"] for m in groups["bundled"]] == [
        "anchor-pdfs",
        "anchor-fmus",
        "anchor-cad",
        "anchor-sysml",
    ]


def test_discover_third_party_manifest_paths_is_stable(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    system_dir = config_home / "oip" / "producers.d"
    project_dir = project_producers_dir(tmp_path / "anchor-data")
    system_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    (project_dir / "beta.json").write_text("{}", encoding="utf-8")
    (project_dir / "alpha.json").write_text("{}", encoding="utf-8")
    (system_dir / "shared.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    paths = discover_third_party_manifest_paths(tmp_path / "anchor-data")

    assert [p.name for p in paths] == ["shared.json", "alpha.json", "beta.json"]


def test_load_manifest_reports_invalid_manifest(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    errors: list[str] = []

    assert load_manifest(bad, on_error=errors.append) is None
    assert errors
    assert "missing oip_version/producer" in errors[0]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "root must be an object"),
        ({"oip_version": "0.1", "producer": "broken"}, "producer must be an object"),
        (
            {"oip_version": "0.1", "producer": {"name": "../outside"}},
            "producer.name",
        ),
    ],
)
def test_load_manifest_rejects_unsafe_shapes(tmp_path, payload, message):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    errors: list[str] = []

    assert load_manifest(bad, on_error=errors.append) is None
    assert message in errors[0]


def test_registration_dir_resolves_scopes(tmp_path, monkeypatch):
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    assert registration_dir("project", tmp_path) == project_producers_dir(tmp_path)
    assert registration_dir("system", tmp_path) == system_producers_dir()


def test_registration_paths_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="scope"):
        registration_dir("typo", tmp_path)
    with pytest.raises(ValueError, match="producer.name"):
        registration_path("project", tmp_path, "../../outside")
