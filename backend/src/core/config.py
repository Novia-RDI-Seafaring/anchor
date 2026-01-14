# Backend Configuration Service
#
# This file provides configuration management for the backend using Pydantic Settings.
# Environment variables are loaded from .env file automatically.

import os
import warnings
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
    
    # ===== Logfire (Observability) =====
    logfire_token: str | None = None
    
    # ===== pgvector/Supabase Settings =====
    # SECURITY: Critical fields with validation
    pgvector_host: str = Field(default="localhost", description="PostgreSQL host")
    pgvector_port: int = Field(default=6543, ge=1, le=65535, description="PostgreSQL port")
    pgvector_db: str = Field(default="postgres", min_length=1, description="Database name")
    pgvector_user: str = Field(default="postgres", min_length=1, description="Database user")
    pgvector_password: str = Field(default="", description="Database password (required in production)")
    pgsslmode: str = Field(default="disable", description="SSL mode: disable, allow, prefer, require, verify-ca, verify-full")
    db_schema: str = "anchor"  # or use "public"
    
    # ===== Vector DB Settings =====
    vector_db_collection: str = "documents"
    embedding_dimension: int = 3072  # text-embedding-3-large dimension
    
    # ===== RAG Configuration =====
    chunk_size: int = Field(default=512, ge=100, le=2000, description="Chunk size in tokens")
    chunk_overlap: int = Field(default=50, ge=0, le=500, description="Chunk overlap in tokens")
    top_k_results: int = Field(default=5, ge=1, le=50, description="Number of search results")
    similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0, description="Similarity threshold")
    
    # ===== Document Storage =====
    uploads_dir: str = "../uploads"
    
    @field_validator('pgvector_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Ensure password is not empty in production."""
        env = os.getenv('ENVIRONMENT', 'development').lower()
        
        if env == 'production':
            if not v or len(v) < 8:
                raise ValueError(
                    "Production database password must be at least 8 characters. "
                    "Set PGVECTOR_PASSWORD environment variable."
                )
        elif not v:
            warnings.warn(
                "Database password is empty! This is acceptable for local development only.",
                UserWarning
            )
        
        return v
    
    @field_validator('pgsslmode')
    @classmethod
    def validate_ssl_mode(cls, v: str) -> str:
        """Warn if SSL is disabled, enforce in production."""
        allowed_modes = ['disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full']
        
        if v not in allowed_modes:
            raise ValueError(f"Invalid SSL mode: {v}. Must be one of {allowed_modes}")
        
        env = os.getenv('ENVIRONMENT', 'development').lower()
        
        if v == 'disable' and env == 'production':
            raise ValueError(
                "SSL cannot be disabled in production! "
                "Set PGSSLMODE to 'require' or higher for security."
            )
        elif v == 'disable':
            warnings.warn(
                "SSL is DISABLED. This is insecure for production deployments!",
                UserWarning
            )
        
        return v
    
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
    def database_url(self) -> str:
        """Build PostgreSQL connection URL from components."""
        return (
            f"postgresql://{self.pgvector_user}:{self.pgvector_password}"
            f"@{self.pgvector_host}:{self.pgvector_port}/{self.pgvector_db}"
            f"?sslmode={self.pgsslmode}"
        )
    
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
