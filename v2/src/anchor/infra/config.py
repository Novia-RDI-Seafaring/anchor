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

    data_dir: Path = Field(default=Path("./data"))
    http_host: str = "0.0.0.0"
    http_port: int = 8002

    openai_api_key: SecretStr | None = None
    embed_model: str = "text-embedding-3-large"
    polish_model: str = "gpt-5.4"
    region_model: str = "gpt-5.4"
    dpi: int = 150

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
