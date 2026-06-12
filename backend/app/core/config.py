"""Runtime settings, env-prefixed ATLAS_; field names mirror .env.example exactly."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATLAS_", env_file=".env", extra="ignore")

    env: str = "dev"
    # SQLite default so the app boots with zero configuration; Postgres via .env.
    database_url: str = "sqlite+aiosqlite:///./atlas.db"
    jwt_secret: str = "change-me"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 1209600
    # NoDecode: pydantic-settings would otherwise JSON-decode list fields before
    # validators run; the env var is a plain comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
