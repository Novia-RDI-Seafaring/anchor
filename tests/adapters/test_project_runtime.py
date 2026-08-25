from __future__ import annotations

import pytest

from anchor.adapters import project_runtime
from anchor.adapters.project_runtime import RuntimeProfile, build_project_runtime
from anchor.infra.config import AnchorConfig


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_LOCAL_EMBEDDER_PRELOAD", "0")
    return AnchorConfig(data_dir=tmp_path / "anchor-data", _env_file=None)


def test_canvas_profile_does_not_build_ingest(config, monkeypatch):
    def fail_if_built(*_args, **_kwargs):
        raise AssertionError("canvas profile must not build PDF ingest")

    monkeypatch.setattr(project_runtime, "build_ingest_service", fail_if_built)

    runtime = build_project_runtime(config, profile=RuntimeProfile.CANVAS)

    assert runtime.profile is RuntimeProfile.CANVAS
    assert runtime.ingest is None
    assert runtime.workspace is not None


def test_ingest_profile_excludes_unrelated_runtime_modules(config):
    runtime = build_project_runtime(config, profile=RuntimeProfile.INGEST)

    assert runtime.require_ingest() is runtime.ingest
    assert runtime.intents is None
    assert runtime.ingest_session is None
    assert runtime.cad is None
    assert runtime.fmu is None
    assert runtime.sysml is None
    assert runtime.synopsis is None


def test_reduced_profile_reports_missing_ingest(config):
    runtime = build_project_runtime(config, profile=RuntimeProfile.CANVAS)

    with pytest.raises(RuntimeError, match="canvas.*does not include PDF ingest"):
        runtime.require_ingest()


def test_full_profile_records_optional_fmu_failure(config, monkeypatch):
    from anchor.extensions.anchor_fmus import extension as fmu_extension

    def fail_fmu(*_args, **_kwargs):
        raise RuntimeError("fmu unavailable")

    monkeypatch.setattr(fmu_extension, "build_service", fail_fmu)
    warnings: list[Exception] = []

    runtime = build_project_runtime(
        config,
        profile=RuntimeProfile.FULL,
        fmu_warning=warnings.append,
    )

    assert runtime.fmu is None
    assert runtime.extension_status["anchor-cad"].available is True
    assert runtime.extension_status["anchor-sysml"].available is True
    fmu_status = runtime.extension_status["anchor-fmus"]
    assert fmu_status.available is False
    assert fmu_status.reason == "fmu unavailable"
    assert fmu_status.error_type == "RuntimeError"
    assert [str(exc) for exc in warnings] == ["fmu unavailable"]
