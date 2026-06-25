"""AnchorConfig — single source of truth for runtime config.

Resolution order (highest precedence first): explicit constructor args,
`ANCHOR_*` environment variables, a `.env` file, a project `anchor.toml`,
then field defaults. The `anchor.toml` is discovered by walking up from
the current directory (or pointed at directly via `ANCHOR_CONFIG`), so a
project's configuration is honored regardless of which directory a process
— including an agent-launched `anchor-mcp` — starts in.

Secrets (the OpenAI/Azure key) are intentionally NOT part of the toml: keep
them in `ANCHOR_OPENAI_API_KEY` / `.env` so a committable config never
carries credentials. Core code never sees AnchorConfig — services receive
the resolved port instances built from the config.
"""
from __future__ import annotations

import contextvars
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

#: Filename for the project-local, non-secret configuration.
CONFIG_FILENAME = "anchor.toml"

#: Pre-merged config values supplied by the environment/project resolver.
#:
#: When set, ``settings_customise_sources`` uses these mapping values as the
#: toml-level source instead of walking up for an ``anchor.toml``. The resolver
#: (``anchor.infra.environment``) layers the environment ``env.toml`` under
#: the project ``anchor.toml`` and parks the result here, so a single
#: ``AnchorConfig`` carries the resolved layering while ``ANCHOR_*`` env vars
#: and explicit constructor args still win above it. Unset for every direct
#: ``AnchorConfig()`` caller, which keeps the legacy walk-up behavior intact.
_ACTIVE_LAYERS: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "anchor_active_config_layers", default=None
)


def _load_toml_tolerant(path: Path) -> dict[str, Any]:
    """Parse an ``anchor.toml``, tolerating a non-UTF-8 (legacy Windows) write.

    TOML mandates UTF-8, but ``anchor init`` run under a Windows locale once
    wrote the file as cp1252 (e.g. an em-dash saved as byte ``0x97``), which a
    strict UTF-8 parse rejects — silently dropping the project's whole config
    and falling back to the global default data dir. Decode ``utf-8-sig``
    first (this also strips a BOM some editors add), fall back to cp1252, so
    such a file still loads instead of being ignored.
    """
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return tomllib.loads(text)


class _MappingSettingsSource(PydanticBaseSettingsSource):
    """Feed an already-parsed toml mapping into settings as one source."""

    def __init__(self, settings_cls: type[BaseSettings], values: dict[str, Any]) -> None:
        super().__init__(settings_cls)
        self._values = values

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return self._values.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return dict(self._values)


def discover_config_file() -> Path | None:
    """Locate the active `anchor.toml`.

    `ANCHOR_CONFIG` (an absolute or ~-relative path) wins when set and points
    at a real file. Otherwise walk up from the current working directory and
    return the first `anchor.toml` found, so any process started anywhere
    inside a project tree resolves the same config. Returns None when nothing
    is found.
    """
    explicit = os.environ.get("ANCHOR_CONFIG")
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None
    cwd = Path.cwd()
    for directory in (cwd, *cwd.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


class AnchorConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANCHOR_", env_file=".env", extra="ignore")

    data_dir: Path = Field(default_factory=lambda: Path.home() / "anchor-data")

    @field_validator("data_dir", mode="after")
    @classmethod
    def _expand_data_dir(cls, value: Path) -> Path:
        """Expand ``~`` and ``$VAR`` in ``data_dir``, from whatever source.

        A ``data_dir`` written as ``~/anchor-data`` or ``$HOME/anchor-data``
        in ``anchor.toml`` (or ``ANCHOR_DATA_DIR`` / ``--data-dir``) parses
        into a literal ``Path`` with no expansion, so a leading ``~`` silently
        becomes a real ``./~`` folder inside the project and every store reads
        from the wrong place. Every source funnels through this validator, so
        expanding here fixes the tilde once for all adapters rather than at
        each call site.
        """
        return Path(os.path.expandvars(str(value))).expanduser()
    # Loopback by default: the HTTP server is unauthenticated and edits
    # local engineering data. Users who want LAN access can opt in via
    # ``ANCHOR_HTTP_HOST=0.0.0.0`` or ``--host 0.0.0.0``, and at that
    # point are responsible for adding their own reverse proxy / auth.
    http_host: str = "127.0.0.1"
    http_port: int = 8002

    # The provider chosen by `anchor init` (see anchor.infra.providers). Purely
    # a record of intent: it does not change wiring on its own — the endpoint /
    # models below do — but it lets the status surface name the active data zone.
    provider: str | None = None

    openai_api_key: SecretStr | None = None
    # Override `openai_base_url` to point at any OpenAI-compatible
    # endpoint: Azure OpenAI, Ollama (`http://localhost:11434/v1`), vLLM,
    # LM Studio, etc. Leave None for stock OpenAI. Used by both the
    # vision-LLM polish and region extraction infra impls.
    openai_base_url: str | None = None
    # Local-only / no-egress mode. A property of the data zone, not a new
    # mechanism: when true, ingest + embed run with no external network calls
    # at all. No OpenAI client is built for polish / region / embeddings
    # regardless of key presence, and model loading is pinned offline
    # (`HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE`) so cached weights load without
    # reaching huggingface.co. Set by the ``local`` provider at `anchor init`
    # time, or directly via ``ANCHOR_LOCAL_ONLY=1`` / ``local_only = true`` in a
    # project's anchor.toml. Run ``anchor models prefetch`` once first so the
    # required weights are cached before an offline run.
    local_only: bool = False
    embed_model: str = "BAAI/bge-small-en-v1.5"
    polish_model: str = "gpt-5.4"
    region_model: str = "gpt-5.4"
    dpi: int = 150

    # Docling accelerator device for the bronze extraction stage. "auto" uses
    # CUDA when present, else CPU — it deliberately skips MPS, because docling's
    # layout model needs float64 (which MPS can't do), so MPS fails for every
    # document on Apple Silicon. Pin a backend with ANCHOR_DOCLING_DEVICE=
    # cpu|cuda|mps; an explicitly-pinned GPU still falls back to CPU on an
    # accelerator error.
    docling_device: str = "auto"

    log_level: str = "INFO"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Insert the discovered `anchor.toml` below env/.env in precedence.

        Order returned is highest-precedence first: constructor args, then
        `ANCHOR_*` env, then `.env`, then `anchor.toml`, then secret files.
        Keeping env above the toml means an operator's `ANCHOR_*` override
        always wins over a committed project default.
        """
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]
        layers = _ACTIVE_LAYERS.get()
        if layers is not None:
            # The environment/project resolver has already merged the
            # environment env.toml under the project anchor.toml. Use that
            # as the single toml-level source instead of walking up for a stray
            # anchor.toml, so the resolved layering is honored exactly.
            sources.append(_MappingSettingsSource(settings_cls, layers))
        else:
            toml_path = discover_config_file()
            if toml_path is not None:
                try:
                    values = _load_toml_tolerant(toml_path)
                    sources.append(_MappingSettingsSource(settings_cls, values))
                except Exception as exc:  # noqa: BLE001
                    # A malformed project anchor.toml must never brick the CLI:
                    # DEFAULT_DATA_DIR is computed at import time, so a parse
                    # error here would crash every command (including
                    # `init --force` that would fix it). Warn and fall back to
                    # env / defaults instead.
                    print(f"Warning: ignoring unreadable {toml_path}: {exc}", file=sys.stderr)
        sources.append(file_secret_settings)
        return tuple(sources)

    @classmethod
    def from_layers(cls, *, layer_values: dict[str, Any], data_dir: Path) -> AnchorConfig:
        """Build a config from pre-merged environment+project toml values.

        ``layer_values`` are the environment ``env.toml`` overlaid by the
        project ``anchor.toml`` (with ``[meta]`` and any ``data_dir`` stripped
        — storage location is structural, set from the resolved project dir).
        They sit below ``ANCHOR_*`` env vars in precedence, matching a hand
        ``anchor.toml``. ``data_dir`` is forced to the project directory so the
        project, not a stray ``ANCHOR_DATA_DIR``, decides where its documents
        and canvases live.
        """
        token = _ACTIVE_LAYERS.set(dict(layer_values))
        try:
            return cls(data_dir=data_dir)
        finally:
            _ACTIVE_LAYERS.reset(token)

    @property
    def bronze_dir(self) -> Path:
        return self.data_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        return self.data_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        return self.data_dir / "gold"

    @property
    def canvases_dir(self) -> Path:
        return self.data_dir / "canvases"
