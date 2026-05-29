"""AnchorConfig — single source of truth for runtime config.

Env-var prefix: `ANCHOR_`. Loaded once in CLI / __main__; passed into
adapter builders. Core code never sees AnchorConfig — services receive
the resolved port instances built from the config.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AnchorConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANCHOR_", env_file=".env", extra="ignore")

    data_dir: Path = Field(default_factory=lambda: Path.home() / "anchor-data")
    # Loopback by default: the HTTP server is unauthenticated and edits
    # local engineering data. Users who want LAN access can opt in via
    # ``ANCHOR_HTTP_HOST=0.0.0.0`` or ``--host 0.0.0.0``, and at that
    # point are responsible for adding their own reverse proxy / auth.
    http_host: str = "127.0.0.1"
    http_port: int = 8002

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
    # to CPU: docling's MPS path raises "Cannot convert a MPS Tensor to
    # float64" on Apple Silicon, which otherwise breaks ingestion on every
    # Mac. Set ANCHOR_DOCLING_DEVICE=cuda|mps|auto where another backend is
    # faster and known-good.
    docling_device: str = "cpu"

    log_level: str = "INFO"

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
