from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="STK_",
        extra="ignore",
    )

    env: str = "development"
    database_url: str = "postgresql+psycopg://stk_os:stk_os_local_only@localhost:55432/stk_os"
    jwt_secret: str = Field(min_length=32)
    jwt_issuer: str = "stk-os-local"
    access_token_minutes: int = Field(default=15, ge=1, le=60)

    @field_validator("database_url")
    @classmethod
    def database_must_be_postgres_outside_tests(cls, value: str, info: object) -> str:
        # Test dependencies override the session and may use SQLite without changing runtime config.
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("STK_DATABASE_URL deve usar postgresql+psycopg")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
