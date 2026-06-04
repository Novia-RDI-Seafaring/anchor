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

import os
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

#: Filename for the project-local, non-secret configuration.
CONFIG_FILENAME = "anchor.toml"


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
    embed_model: str = "BAAI/bge-small-en-v1.5"
    polish_model: str = "gpt-5.4"
    region_model: str = "gpt-5.4"
    dpi: int = 150

    # Docling accelerator device for the bronze extraction stage. Defaults
    # to CPU: docling's AUTO device resolves to MPS when torch exposes it,
    # and MPS cannot allocate float64 tensors ("Cannot convert a MPS Tensor
    # to float64"). That crashes ingestion on Macs where torch has MPS and
    # the document exercises the float64 model path (e.g. table structure).
    # CPU sidesteps that class of error everywhere, at some speed cost on
    # large docs. Set ANCHOR_DOCLING_DEVICE=cuda|mps|auto where another
    # backend is faster and known-good.
    docling_device: str = "cpu"

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
        toml_path = discover_config_file()
        if toml_path is not None:
            sources.append(TomlConfigSettingsSource(settings_cls, toml_file=toml_path))
        sources.append(file_secret_settings)
        return tuple(sources)

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
