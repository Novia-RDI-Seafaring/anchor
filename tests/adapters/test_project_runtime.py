from __future__ import annotations

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
