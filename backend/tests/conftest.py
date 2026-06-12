"""Shared fixtures — D-025 template-copy isolation: one migrated SQLite template per
session, copied per test, so real commits are allowed and nothing leaks across tests."""

import shutil
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.db import build_engine, build_session_factory, get_session
from app.core.tenancy import system_context
from app.main import create_app
from app.modules.admin.models import Tenant
from app.modules.admin.service import provision_tenant, provision_user

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def make_alembic_config() -> Callable[[str], Config]:
    def _make(database_url: str) -> Config:
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        # config.attributes outranks ATLAS_DATABASE_URL in env.py, so a developer's
        # shell environment can never redirect test migrations.
        config.attributes["sqlalchemy_url"] = database_url
        return config

    return _make


@pytest.fixture(scope="session")
def template_db_path(
    tmp_path_factory: pytest.TempPathFactory,
    make_alembic_config: Callable[[str], Config],
) -> Path:
    """Build ONE migrated template database for the whole session. The Alembic head
    revision is embedded in the filename so a new migration changes the template
    identity automatically (D-025)."""
    script_dir = ScriptDirectory.from_config(make_alembic_config("sqlite+aiosqlite://"))
    head = script_dir.get_current_head()
    path = tmp_path_factory.mktemp("template") / f"template_{head}.sqlite"
    # Sync session-scoped fixture: env.py's asyncio.run works (no running loop here).
    command.upgrade(make_alembic_config(f"sqlite+aiosqlite:///{path}"), "head")
    return path


@pytest.fixture
async def db_engine(template_db_path: Path, tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    db_path = tmp_path / "test.sqlite"
    shutil.copy(template_db_path, db_path)
    engine = build_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with build_session_factory(db_engine)() as session:
        yield session


@pytest.fixture
def app(db_engine: AsyncEngine) -> FastAPI:
    application = create_app()
    factory = build_session_factory(db_engine)

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    application.dependency_overrides[get_session] = _override_get_session
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    # https base_url so the D-008 Secure refresh cookie is actually sent back by httpx
    # (it withholds Secure cookies over http), matching the production HTTPS deploy.
    async with AsyncClient(transport=transport, base_url="https://test") as test_client:
        yield test_client


async def _create_tenant(session: AsyncSession, slug: str) -> uuid.UUID:
    # system_context mirrors the real provisioning path (D-007 sanctioned site 2).
    with system_context():
        tenant = Tenant(slug=slug, name=slug.replace("-", " ").title())
        session.add(tenant)
        await session.commit()
    return tenant.id


@pytest.fixture
async def tenant_a(db_session: AsyncSession) -> uuid.UUID:
    return await _create_tenant(db_session, "tenant-a")


@pytest.fixture
async def tenant_b(db_session: AsyncSession) -> uuid.UUID:
    return await _create_tenant(db_session, "tenant-b")


# --- Auth fixtures (D-008 / D-025): real provisioning + login ------------------


@dataclass(frozen=True)
class ProvisionedUser:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


@pytest.fixture
def user_factory(
    db_session: AsyncSession,
) -> Callable[..., "AsyncIterator[ProvisionedUser]"]:
    """Provision a tenant + user through the REAL admin service under system_context
    (D-025: factories go through real services). Returns a coroutine the test awaits."""

    async def _create(
        slug: str = "acme",
        email: str = "owner@acme.test",
        password: str = "correct-horse-battery",
    ) -> ProvisionedUser:
        tenant = await provision_tenant(db_session, slug=slug, name=slug.title())
        user = await provision_user(db_session, tenant.id, email=email, password=password)
        await db_session.commit()
        return ProvisionedUser(
            tenant_id=tenant.id,
            tenant_slug=slug,
            user_id=user.id,
            email=email,
            password=password,
        )

    return _create


@pytest.fixture
async def provisioned_user(
    user_factory: Callable[..., AsyncIterator[ProvisionedUser]],
) -> ProvisionedUser:
    return await user_factory()


async def _login(client: AsyncClient, principal: ProvisionedUser) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture
async def authed_client(
    client: AsyncClient, provisioned_user: ProvisionedUser
) -> AsyncIterator[AsyncClient]:
    """A client with a real bearer token attached — reused by later module tests."""
    access_token = await _login(client, provisioned_user)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield client
