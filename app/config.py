"""
Application Configuration
==========================
All settings loaded from environment variables with sensible defaults.
Use a .env file locally; inject real secrets via environment in production.
"""

from __future__ import annotations
from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql+asyncpg://freight:freight_pass@localhost:5432/freight_db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "Freight Bill Processor"
    debug: bool = False
    log_level: str = "INFO"
    log_dir: str = "logs"
    log_file_name: str = "app.log"
    log_max_bytes: int = 5_242_880  # 5 MB
    log_backup_count: int = 5

    # Database — async driver required
    database_url: str = DEFAULT_DATABASE_URL

    # Durable worker and checkpoint infrastructure
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_always_eager: bool = False
    checkpoint_pool_size: int = 5

    # Multi-tenancy
    default_tenant_id: str = "default"

    # Authentication bootstrap user. Replace with DB-backed users before public deployment.
    admin_username: str = "admin"
    admin_password: str = "admin"
    demo_tenant_id: str = "demo"
    demo_username: str = "demo"
    demo_password: str = "demo"

    # LLM — at least one key required for LLM features
    llm_provider: str = "anthropic"          # "openai" | "anthropic"
    llm_openai_model: str = "gpt-4o-mini"
    llm_anthropic_model: str = "claude-3-5-haiku-latest"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_debug_payloads: bool = False
    llm_circuit_breaker_cooldown_seconds: int = 60

    # Graph backend
    graph_backend: str = "neo4j"            # "neo4j" | "memory"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    neo4j_max_connection_pool_size: int = 50

    # Agent thresholds
    auto_approve_threshold: float = 0.85     # confidence >= this → auto_approve
    dispute_threshold: float = 0.40          # confidence <= this → dispute (not just flag)

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str | None) -> str:
        """
        Prevent empty DATABASE_URL values in .env from crashing startup.
        If blank, fall back to local default.
        """
        if value is None:
            return DEFAULT_DATABASE_URL
        if isinstance(value, str) and not value.strip():
            return DEFAULT_DATABASE_URL
        return value

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: bool | str | None) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
