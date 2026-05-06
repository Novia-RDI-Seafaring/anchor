# Backend Configuration Service
#
# This file provides configuration management for the backend using Pydantic Settings.
# Environment variables are loaded from .env file automatically.

import os
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """
    Application settings loaded from environment variables with security validation.
    
    Create a .env file in the backend directory with your configuration.
    See .env.example for template.
    """
    
    # ===== API Settings =====
    host: str = "0.0.0.0"
    port: int = 8001
    reload: bool = True

    # ===== Model / Context Configuration =====
    default_model: str = Field(default="openai:gpt-4o-mini", description="PydanticAI model string")
    # full_context_mode: "auto" | "true" | "false"
    # auto = enabled when model name matches a known large-context model (gpt-5, etc.)
    full_context_mode: str = Field(default="auto", description="Full-document context mode")

    _LARGE_CONTEXT_PATTERNS = ("gpt-5", "o3", "claude-3-7", "claude-3-5", "gemini-1.5", "gemini-2")

    @property
    def is_full_context_mode(self) -> bool:
        mode = self.full_context_mode.strip().lower()
        if mode == "true":
            return True
        if mode == "false":
            return False
        # auto: check DEFAULT_MODEL env var directly (Settings field may not be set)
        model = (os.getenv("DEFAULT_MODEL") or self.default_model).lower()
        return any(p in model for p in self._LARGE_CONTEXT_PATTERNS)

    # ===== RAG Configuration =====
    chunk_size: int = Field(default=512, ge=100, le=2000, description="Chunk size in tokens")
    chunk_overlap: int = Field(default=50, ge=0, le=500, description="Chunk overlap in tokens")
    top_k_results: int = Field(default=5, ge=1, le=50, description="Number of search results")
    similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0, description="Similarity threshold")
    
    # ===== Document Storage =====
    uploads_dir: str = "../uploads"  # legacy, unused — bronze dir is under data_dir

    @field_validator('chunk_overlap')
    @classmethod
    def validate_chunk_overlap(cls, v: int, info) -> int:
        """Ensure overlap is less than chunk size."""
        chunk_size = info.data.get('chunk_size', 512)
        if v >= chunk_size:
            raise ValueError(
                f"Chunk overlap ({v}) must be less than chunk size ({chunk_size})"
            )
        return v

    @property
    def backend_dir(self) -> Path:
        """Backend project root, independent of the process working directory."""
        return Path(__file__).resolve().parents[2]

    @property
    def data_dir(self) -> Path:
        """Root data directory.  Set ANCHOR_DATA_DIR to override."""
        env = os.environ.get("ANCHOR_DATA_DIR")
        if env:
            return Path(env).resolve()
        return Path("data").resolve()

    @property
    def bronze_dir(self) -> Path:
        """Bronze layer — raw uploaded PDFs live here."""
        return self.data_dir / "bronze"

    @property
    def uploads_path(self) -> Path:
        """Alias for bronze_dir (backward compat)."""
        return self.bronze_dir
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra env vars

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance with validation."""
    try:
        settings = Settings()
        return settings
    except Exception as e:
        print("\nConfiguration Error:")
        print(f"{str(e)}\n")
        print("Ensure all required environment variables are set in your .env file.")
        print("See .env.example for template.\n")
        raise
