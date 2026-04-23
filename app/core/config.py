from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "Crypto Brokerage API"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = Field(default="development", pattern="^(development|staging|production)$")

    # ── Database ─────────────────────────────────────────────────────────────
    # Example: postgresql+asyncpg://user:password@localhost:5432/brokerage
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://brokerage:brokerage@localhost:5432/brokerage"
    )
    # SQLAlchemy pool settings
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800  # recycle connections every 30 min

    # ── Auth / JWT ────────────────────────────────────────────────────────────
    # IMPORTANT: Override via environment variable in all non-development environments.
    jwt_secret_key: SecretStr = Field(default="CHANGE_ME_IN_PRODUCTION_USE_STRONG_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # ── Integration Gateways ──────────────────────────────────────────────────
    exchange_api_url: str = "https://api.exchange.example.com"
    exchange_api_key: SecretStr = Field(default="stub_key")
    exchange_api_secret: SecretStr = Field(default="stub_secret")

    banking_api_url: str = "https://api.banking.example.com"
    banking_api_key: SecretStr = Field(default="stub_key")

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_allowed_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"]
    )

    # ── Default Account ───────────────────────────────────────────────────────
    default_account_currency: str = "BRL"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings singleton. Use as a FastAPI dependency."""
    return Settings()
