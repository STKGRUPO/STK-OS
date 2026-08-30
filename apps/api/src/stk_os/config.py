from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    operational_timezone: str = "America/Sao_Paulo"
    billing_rule_version: str = "billing-competence-v1"
    fiscal_environment: str = "homologation"
    fiscal_document_root: Path = Path(".stk-private/fiscal-documents")
    fiscal_service_url: str = "https://fiscal-service.internal"
    fiscal_service_token_file: Path = Path("/run/secrets/stk-fiscal-service/token")
    fiscal_service_token: str = ""
    fiscal_timeout_seconds: int = Field(default=60, ge=5, le=120)

    @field_validator("database_url")
    @classmethod
    def database_must_be_postgres_outside_tests(cls, value: str, info: object) -> str:
        # Test dependencies override the session and may use SQLite without changing runtime config.
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("STK_DATABASE_URL deve usar postgresql+psycopg")
        return value

    @field_validator("operational_timezone")
    @classmethod
    def timezone_must_be_explicit_and_valid(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("STK_OPERATIONAL_TIMEZONE deve ser um timezone IANA válido") from error
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
