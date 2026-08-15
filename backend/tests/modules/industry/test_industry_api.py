"""PLAN 14.1 / D-060: the industry HTTP surface — list/get templates + the idempotent apply
endpoint, with RBAC and tenant isolation.

Drives /api/v1/industry over the wire with a bearer-token principal holding the industry keys
(conftest), proving: the template catalog + a single parsed template read; apply instantiates the
slices (a finance account appears) and is idempotent (created=false on re-apply); the read/apply
permissions are enforced (403); a tenant admin cannot apply to ANOTHER tenant (D-007 isolation).
"""

import uuid

from sqlalchemy import func, select

from app.core.tenancy import system_context
from app.modules.finance.models import Account
from app.modules.industry.constants import INDUSTRY_TEMPLATE_READ, SHIPPED_TEMPLATES


async def test_list_templates_returns_every_shipped_template(industry_api):
    """The catalog the onboarding wizard renders is exactly SHIPPED_TEMPLATES — a template added to
    the tuple but not shipped as a file (or the reverse) fails here, not at a tenant's first
    apply."""
    response = await industry_api.client.get("/api/v1/industry/templates")
    assert response.status_code == 200, response.text
    names = {row["name"] for row in response.json()}
    assert names == set(SHIPPED_TEMPLATES)


async def test_get_template_returns_parsed_content(industry_api):
    response = await industry_api.client.get("/api/v1/industry/templates/healthcare")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["terminology"]["customer"] == "Patient"
    assert body["modules"]["manufacturing"] is False
    assert len(body["chart_of_accounts"]["accounts"]) >= 1


async def test_get_unknown_template_is_404(industry_api):
    response = await industry_api.client.get("/api/v1/industry/templates/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "industry.template_not_found"


async def test_apply_endpoint_instantiates_and_is_idempotent(industry_api, db_session):
    tenant_id = industry_api.principal.tenant_id
    first = await industry_api.client.post(
        f"/api/v1/industry/tenants/{tenant_id}/apply?template=manufacturing"
    )
    assert first.status_code == 201, first.text
    assert first.json() == {
        "tenant_id": str(tenant_id),
        "template_name": "manufacturing",
        "created": True,
    }
    # The finance handler created the COA over the wire.
    with system_context():
        count = (
            await db_session.execute(
                select(func.count()).select_from(Account).where(Account.tenant_id == tenant_id)
            )
        ).scalar_one()
    assert count == 13

    # Re-apply: 201 no-op, created=false.
    second = await industry_api.client.post(
        f"/api/v1/industry/tenants/{tenant_id}/apply?template=manufacturing"
    )
    assert second.status_code == 201, second.text
    assert second.json()["created"] is False


async def test_apply_endpoint_rejects_template_switch(industry_api):
    tenant_id = industry_api.principal.tenant_id
    await industry_api.client.post(
        f"/api/v1/industry/tenants/{tenant_id}/apply?template=manufacturing"
    )
    switch = await industry_api.client.post(
        f"/api/v1/industry/tenants/{tenant_id}/apply?template=retail"
    )
    assert switch.status_code == 409
    assert switch.json()["error"]["code"] == "industry.template_conflict"


async def test_read_endpoint_requires_read_permission(
    client, industry_user_factory
):
    # A principal with NO industry keys.
    principal = await industry_user_factory(slug="no-keys", email="x@no-keys.test", keys=())
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    response = await client.get("/api/v1/industry/templates")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "rbac.permission_denied"


async def test_apply_requires_apply_permission(client, industry_user_factory):
    # A read-only principal cannot apply.
    principal = await industry_user_factory(
        slug="read-only", email="r@read-only.test", keys=(INDUSTRY_TEMPLATE_READ,)
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
        f"/api/v1/industry/tenants/{principal.tenant_id}/apply?template=manufacturing"
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "rbac.permission_denied"


async def test_apply_to_another_tenant_is_denied(industry_api):
    """A tenant admin cannot provision a DIFFERENT tenant (D-007 isolation) — reported as a
    permission denial so cross-tenant existence is not probeable."""
    other_tenant = uuid.uuid4()
    response = await industry_api.client.post(
        f"/api/v1/industry/tenants/{other_tenant}/apply?template=manufacturing"
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "rbac.tenant_mismatch"
