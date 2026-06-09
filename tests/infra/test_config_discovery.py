"""AnchorConfig resolves a project anchor.toml, with env taking precedence."""
from __future__ import annotations

from anchor.infra.config import AnchorConfig, discover_config_file

_CLEAR = (
    "ANCHOR_CONFIG",
    "ANCHOR_DATA_DIR",
    "ANCHOR_EMBED_MODEL",
    "ANCHOR_POLISH_MODEL",
    "ANCHOR_DOCLING_DEVICE",
)


def _clean_env(monkeypatch):
    for name in _CLEAR:
        monkeypatch.delenv(name, raising=False)


def test_anchor_toml_discovered_by_walkup(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    (tmp_path / "anchor.toml").write_text(
        'embed_model = "test-embed"\npolish_model = "test-polish"\n'
    )
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    assert discover_config_file() == tmp_path / "anchor.toml"
    cfg = AnchorConfig()
    assert cfg.embed_model == "test-embed"
    assert cfg.polish_model == "test-polish"


def test_env_overrides_toml(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    (tmp_path / "anchor.toml").write_text('embed_model = "from-toml"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANCHOR_EMBED_MODEL", "from-env")

    assert AnchorConfig().embed_model == "from-env"


def test_anchor_config_env_points_at_explicit_file(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    cfg_file = tmp_path / "custom.toml"
    cfg_file.write_text('docling_device = "cuda"\n')
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)  # no anchor.toml here
    monkeypatch.setenv("ANCHOR_CONFIG", str(cfg_file))

    assert discover_config_file() == cfg_file
    assert AnchorConfig().docling_device == "cuda"


def test_malformed_toml_is_ignored_not_fatal(tmp_path, monkeypatch):
    # Reproduces the field-with-ANSI-escape corruption: an unparseable
    # anchor.toml must warn and fall back, never crash the CLI at import.
    _clean_env(monkeypatch)
    (tmp_path / "anchor.toml").write_text('embed_model = "bad\x1bvalue"\n')
    monkeypatch.chdir(tmp_path)
    cfg = AnchorConfig()  # must not raise
    assert cfg.embed_model == "BAAI/bge-small-en-v1.5"  # fell back to default


def test_missing_config_falls_back_to_defaults(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    assert discover_config_file() is None
    assert AnchorConfig().docling_device == "auto"
