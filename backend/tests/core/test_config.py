"""Settings validation — the prod JWT-secret startup guard (#77)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings(**overrides: object) -> Settings:
    # _env_file=None: keep a developer's local .env from leaking into the test.
    return Settings(_env_file=None, **overrides)


def test_prod_refuses_default_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="ATLAS_JWT_SECRET"):
        _settings(env="prod", jwt_secret="change-me")


def test_production_alias_also_guarded() -> None:
    with pytest.raises(ValidationError, match="ATLAS_JWT_SECRET"):
        _settings(env="production", jwt_secret="change-me")


def test_prod_refuses_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="ATLAS_JWT_SECRET"):
        _settings(env="prod", jwt_secret="short-secret")


def test_prod_accepts_real_jwt_secret() -> None:
    settings = _settings(env="prod", jwt_secret="x" * 32)
    assert settings.env == "prod"


def test_dev_still_boots_with_default_secret() -> None:
    settings = _settings()
    assert settings.jwt_secret == "change-me"
