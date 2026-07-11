from __future__ import annotations

import json

import pytest

from anchor.adapters.extension_host import (
    bundled_manifests,
    discover_manifests,
    discover_third_party_manifest_paths,
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
    assert names == ["anchor-pdfs", "anchor-fmus", "anchor-cad"]
    assert "anchor-sysml" not in names


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
