"""Runtime settings, env-prefixed ATLAS_; field names mirror .env.example exactly."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_MIN_JWT_SECRET_LENGTH = 32


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
    # D-010 audit context: honor the left-most X-Forwarded-For hop ONLY when the app
    # sits behind a trusted proxy. Default false — read request.client.host directly so
    # a client can never spoof its audited IP by sending the header itself.
    trust_proxy: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _require_real_jwt_secret_in_prod(self) -> "Settings":
        # Auth invariant: the repo is public, so the default secret means anyone
        # can forge a token for any user/tenant. Refuse to boot in prod with it.
        if self.env in {"prod", "production"} and (
            self.jwt_secret == "change-me" or len(self.jwt_secret) < _MIN_JWT_SECRET_LENGTH
        ):
            raise ValueError(
                "ATLAS_JWT_SECRET must be set to a random value of at least "
                f"{_MIN_JWT_SECRET_LENGTH} characters when ATLAS_ENV is "
                f"{self.env!r} — generate one: "
                'python -c "import secrets; print(secrets.token_urlsafe(64))"'
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
