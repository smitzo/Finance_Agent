"""
Application Configuration
==========================
All settings loaded from environment variables with sensible defaults.
Use a .env file locally; inject real secrets via environment in production.
"""

from __future__ import annotations
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "Freight Bill Processor"
    debug: bool = False

    # Database — async driver required
    database_url: str = "postgresql+asyncpg://freight:freight_pass@localhost:5432/freight_db"

    # LLM — at least one key required for LLM features
    llm_provider: str = "anthropic"          # "openai" | "anthropic"
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Agent thresholds
    auto_approve_threshold: float = 0.85     # confidence >= this → auto_approve
    dispute_threshold: float = 0.40          # confidence <= this → dispute (not just flag)


@lru_cache
def get_settings() -> Settings:
    return Settings()
