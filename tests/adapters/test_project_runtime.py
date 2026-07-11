from __future__ import annotations

from anchor.adapters import project_runtime
from anchor.adapters.project_runtime import build_project_runtime
from anchor.infra.config import AnchorConfig


def test_project_runtime_records_optional_extension_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("ANCHOR_LOCAL_EMBEDDER_PRELOAD", "0")

    from anchor.extensions.anchor_fmus import extension as fmu_ext

    def fail_fmu(*_args, **_kwargs):
        raise RuntimeError("fmu unavailable")

    monkeypatch.setattr(fmu_ext, "build_service", fail_fmu)
    warnings: list[Exception] = []

    runtime = build_project_runtime(
        AnchorConfig(data_dir=tmp_path / "anchor-data", _env_file=None),
        include_intents=False,
        include_ingest_session=False,
        include_synopsis=False,
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


def test_project_runtime_can_omit_keyed_pdf_ingest(tmp_path, monkeypatch):
    def fail_if_built(*_args, **_kwargs):
        raise AssertionError("keyed PDF ingest should not be built")

    monkeypatch.setattr(project_runtime, "build_ingest_service", fail_if_built)

    runtime = build_project_runtime(
        AnchorConfig(data_dir=tmp_path / "anchor-data", _env_file=None),
        include_ingest=False,
        include_intents=False,
        include_ingest_session=False,
        include_extensions=False,
        include_synopsis=False,
    )

    assert runtime.ingest is None
    assert runtime.workspace is not None
