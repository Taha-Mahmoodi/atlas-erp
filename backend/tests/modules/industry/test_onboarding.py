"""PLAN 14.2 / D-061: the tenant onboarding wizard provisions a WHOLE tenant — tenant + first admin
role + first admin user + the chosen industry template's slices — in ONE transaction.

Proves (service + API): a fresh onboard creates the tenant, an Administrator role carrying the admin
permission keys, and the admin user; the template is instantiated (COA accounts + UoMs exist + a
terminology TenantSetting is set, read under the NEW tenant's context via the existing queries); the
new admin can authenticate through the real login path; a duplicate slug is a 409; an unknown
template fails cleanly with NO partial tenant (rollback); and the endpoint enforces its platform
permission (403 without it). Handlers are wired by the autouse conftest fixture.

Issue #53: the unknown-template rollback test asserts only the raise + that no tenant exists
afterward (a fresh read), NOT post-failure state probed on the same rolled-back session mid-flight.
"""

import uuid

import pytest
from sqlalchemy import func, select

from app.core.events import run_in_uow
from app.core.exceptions import ConflictError, NotFoundError
from app.core.models import Permission, Role, RolePermission, User, UserRole
from app.core.rbac import (
    ADMIN_TENANT_MANAGE,
    ADMIN_USER_MANAGE,
    sync_permission_catalog,
)
from app.core.tenancy import system_context
from app.modules.admin.models import TenantSetting
from app.modules.admin.service import find_tenant_by_slug
from app.modules.finance.models import Account
from app.modules.industry import onboarding, queries
from app.modules.industry.constants import (
    ONBOARDING_TENANT_CREATE,
    TERMINOLOGY_SETTING_KEY,
)
from app.modules.inventory.models import Uom

_PASSWORD = "correct-horse-battery"


async def _onboard(session, **kwargs) -> onboarding.OnboardingResult:
    """Run onboard_tenant through run_in_uow — the router's exact path (the loader publishes the
    provisioning event, drained in the same transaction). Syncs the permission catalog first,
    mirroring production (synced once at deploy) so grant_admin_role's keys are grantable."""
    with system_context():
        await sync_permission_catalog(session)
    holder: dict[str, onboarding.OnboardingResult] = {}

    async def _work() -> None:
        holder["result"] = await onboarding.onboard_tenant(session, **kwargs)

    await run_in_uow(session, _work)
    return holder["result"]


async def _count(session, model, tenant_id) -> int:
    with system_context():
        stmt = select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
        return (await session.execute(stmt)).scalar_one()


# --- Service-layer flow --------------------------------------------------------


async def test_onboard_creates_tenant_admin_role_and_user(db_session):
    result = await _onboard(
        db_session,
        company_name="Acme Widgets",
        slug="acme-widgets",
        template_name="manufacturing",
        admin_email="owner@acme.test",
        admin_password=_PASSWORD,
    )
    # The tenant exists at the returned slug.
    tenant = await find_tenant_by_slug(db_session, "acme-widgets")
    assert tenant is not None
    assert tenant.id == result.tenant_id
    assert tenant.name == "Acme Widgets"

    # The admin user exists under the new tenant.
    with system_context():
        admin = (
            await db_session.execute(select(User).where(User.id == result.admin_user_id))
        ).scalar_one()
    assert admin.email == "owner@acme.test"
    assert admin.tenant_id == result.tenant_id

    # An Administrator role exists AND carries the admin permission keys (via grant_admin_role).
    with system_context():
        role_keys = (
            await db_session.execute(
                select(Permission.key)
                .select_from(UserRole)
                .join(RolePermission, RolePermission.role_id == UserRole.role_id)
                .join(Permission, Permission.id == RolePermission.permission_id)
                .where(UserRole.user_id == result.admin_user_id)
            )
        ).scalars().all()
    assert ADMIN_USER_MANAGE in role_keys
    assert ADMIN_TENANT_MANAGE in role_keys
    with system_context():
        role_count = (
            await db_session.execute(
                select(func.count()).select_from(Role).where(Role.tenant_id == result.tenant_id)
            )
        ).scalar_one()
    assert role_count == 1


async def test_onboard_instantiates_the_template(db_session):
    result = await _onboard(
        db_session,
        company_name="Mercy Clinic",
        slug="mercy-clinic",
        template_name="healthcare",
        admin_email="admin@mercy.test",
        admin_password=_PASSWORD,
    )
    tenant_id = result.tenant_id
    # COA accounts + UoMs were instantiated for the new tenant.
    assert await _count(db_session, Account, tenant_id) >= 1
    assert await _count(db_session, Uom, tenant_id) >= 1
    # The terminology override the template set, read via the EXISTING industry query.
    terminology = await queries.terminology_for(db_session, tenant_id)
    assert terminology["customer"] == "Patient"
    # A terminology TenantSetting row was written under the new tenant.
    with system_context():
        setting = (
            await db_session.execute(
                select(TenantSetting.value).where(
                    TenantSetting.tenant_id == tenant_id,
                    TenantSetting.key == TERMINOLOGY_SETTING_KEY,
                )
            )
        ).scalar_one()
    assert setting["customer"] == "Patient"
    # The instantiated summary reflects the template's counts.
    assert result.instantiated["accounts"] >= 1
    assert result.instantiated["uoms"] >= 1
    assert result.template_applied == "healthcare"


async def test_onboard_derives_slug_when_omitted(db_session):
    # No slug passed to the SCHEMA is derived in the schema; the service takes an explicit slug, so
    # here we assert the schema derivation feeds a clean slug into the service.
    from app.modules.industry.schemas import OnboardTenantRequest

    payload = OnboardTenantRequest(
        company_name="Bright & Co. Ltd",
        template_name="retail",
        admin_email="a@bright.test",
        admin_password=_PASSWORD,
    )
    assert payload.slug == "bright-co-ltd"


async def test_duplicate_slug_raises_conflict(db_session):
    await _onboard(
        db_session,
        company_name="First Co",
        slug="dup-co",
        template_name="retail",
        admin_email="first@dup.test",
        admin_password=_PASSWORD,
    )
    with pytest.raises(ConflictError) as exc:
        await _onboard(
            db_session,
            company_name="Second Co",
            slug="dup-co",
            template_name="retail",
            admin_email="second@dup.test",
            admin_password=_PASSWORD,
        )
    assert exc.value.code == "onboarding.slug_taken"


async def test_unknown_template_leaves_no_partial_tenant(db_session):
    """#53: assert the raise, then confirm via a FRESH read that no tenant persisted — the whole
    onboard rolls back (D-011), so a half-provisioned tenant can never remain."""
    with pytest.raises(NotFoundError) as exc:
        await _onboard(
            db_session,
            company_name="Ghost Co",
            slug="ghost-co",
            template_name="not-a-real-template",
            admin_email="ghost@ghost.test",
            admin_password=_PASSWORD,
        )
    assert exc.value.code == "industry.template_not_found"
    # Fresh read after the rolled-back transaction: nothing from the failed onboard persists.
    assert await find_tenant_by_slug(db_session, "ghost-co") is None


# --- API surface + RBAC --------------------------------------------------------


async def _platform_client(client, industry_user_factory):
    """A bearer-token client whose principal holds the platform onboarding permission."""
    principal = await industry_user_factory(
        slug="platform-op",
        email="op@platform.test",
        keys=(ONBOARDING_TENANT_CREATE,),
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    return client


async def test_onboard_endpoint_provisions_and_admin_can_authenticate(
    client, industry_user_factory
):
    api = await _platform_client(client, industry_user_factory)
    response = await api.post(
        "/api/v1/onboarding/tenants",
        json={
            "company_name": "Wired Inc",
            "slug": "wired-inc",
            "template_name": "manufacturing",
            "admin_email": "boss@wired.test",
            "admin_password": _PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slug"] == "wired-inc"
    assert body["template_applied"] == "manufacturing"
    assert body["instantiated"]["accounts"] >= 1
    assert uuid.UUID(body["admin_user_id"])

    # The freshly-provisioned admin can log in through the real auth path (proves the user + hash
    # + tenant were committed together).
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": "wired-inc",
            "email": "boss@wired.test",
            "password": _PASSWORD,
        },
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


async def test_onboard_endpoint_rejects_duplicate_slug(client, industry_user_factory):
    api = await _platform_client(client, industry_user_factory)
    payload = {
        "company_name": "Twice Co",
        "slug": "twice-co",
        "template_name": "retail",
        "admin_email": "a@twice.test",
        "admin_password": _PASSWORD,
    }
    first = await api.post("/api/v1/onboarding/tenants", json=payload)
    assert first.status_code == 201, first.text
    payload["admin_email"] = "b@twice.test"
    second = await api.post("/api/v1/onboarding/tenants", json=payload)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "onboarding.slug_taken"


async def test_onboard_endpoint_requires_permission(client, industry_user_factory):
    # A principal WITHOUT the onboarding permission cannot provision a tenant.
    principal = await industry_user_factory(
        slug="no-onboard", email="x@no-onboard.test", keys=()
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    response = await client.post(
        "/api/v1/onboarding/tenants",
        json={
            "company_name": "Denied Co",
            "slug": "denied-co",
            "template_name": "retail",
            "admin_email": "a@denied.test",
            "admin_password": _PASSWORD,
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "rbac.permission_denied"


async def test_onboarding_permission_is_in_catalog(db_session):
    """The platform permission is code-declared, so it can be granted (D-009). Syncing the catalog
    inserts it into core_permissions."""
    with system_context():
        await sync_permission_catalog(db_session)
        keys = (
            await db_session.execute(select(Permission.key))
        ).scalars().all()
    assert ONBOARDING_TENANT_CREATE in keys
