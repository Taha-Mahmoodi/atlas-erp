"""Industry HTTP layer (thin): parse -> call loader/queries -> return schema (PLAN 14.1 / D-060).

REST under ``/api/v1/industry``:

* ``GET  /templates``            — the shipped template catalog (summary per template).
* ``GET  /templates/{name}``     — one fully-parsed template (the COA/fields/etc.).
* ``POST /tenants/{tenant_id}/apply?template=`` — idempotently apply a template to a tenant
  (guarded by ``industry.template.apply``). 14.2's onboarding wizard wraps this; 14.1 exposes it
  directly.

Reads are guarded by ``industry.template.read``; the apply by ``industry.template.apply``. The
apply is tenant-scoped: an admin may apply ONLY to their OWN tenant (the path tenant_id must equal
the caller's) — cross-tenant provisioning is the system/onboarding path (14.2), never a tenant
admin reaching across tenancy (D-007 isolation). The apply commits through ``run_in_uow`` (D-011)
so the cross-module provisioning handlers drain in the same transaction.
"""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.exceptions import PermissionDeniedError
from app.core.rbac import require_permission
from app.modules.industry import loader, onboarding, queries
from app.modules.industry.constants import (
    INDUSTRY_TEMPLATE_APPLY,
    INDUSTRY_TEMPLATE_READ,
    ONBOARDING_TENANT_CREATE,
)
from app.modules.industry.schemas import (
    IndustryTemplate,
    OnboardTenantRequest,
    OnboardTenantResponse,
)

router = APIRouter(prefix="/api/v1/industry", tags=["industry"])
# Onboarding is a PLATFORM surface (creates whole tenants), so it mounts at its own prefix and is
# guarded by onboarding.tenant.create — not the tenant-scoped industry.template.apply (D-061).
onboarding_router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


class TemplateSummary(BaseModel):
    """One row of the shipped-template catalog (the list endpoint) — name + the human labels +
    the module toggles, enough for the onboarding wizard's picker without the full COA payload."""

    name: str
    display_name: str
    description: str
    modules: dict[str, bool]


class ApplyResult(BaseModel):
    """The result of applying a template: which template the tenant now has + whether THIS call
    created it (False ⇒ it was already applied — the idempotent no-op path)."""

    tenant_id: uuid.UUID
    template_name: str
    created: bool


@router.get(
    "/templates",
    response_model=list[TemplateSummary],
    dependencies=[Depends(require_permission(INDUSTRY_TEMPLATE_READ))],
)
async def list_templates() -> list[TemplateSummary]:
    """The five shipped templates as summaries (D-060). Pure read off the bundled YAML."""
    return [
        TemplateSummary(
            name=template.name,
            display_name=template.display_name,
            description=template.description,
            modules=template.modules,
        )
        for template in queries.list_templates()
    ]


@router.get(
    "/templates/{name}",
    response_model=IndustryTemplate,
    dependencies=[Depends(require_permission(INDUSTRY_TEMPLATE_READ))],
)
async def get_template(name: str) -> IndustryTemplate:
    """One fully-parsed template (D-060). Raises 404 industry.template_not_found for an unknown
    name, 422 industry.schema_invalid if the shipped file is malformed (a build error)."""
    return loader.load_template(name)


@router.post(
    "/tenants/{tenant_id}/apply",
    response_model=ApplyResult,
    status_code=201,
)
async def apply_template(
    tenant_id: uuid.UUID,
    template: str,
    current: CurrentUserDep,
    session: SessionDep,
) -> ApplyResult:
    """Idempotently apply an industry template to a tenant (D-060). Guarded by
    ``industry.template.apply`` AND tenant-scoped: the path tenant_id must equal the caller's
    tenant (an admin provisions only their own tenant; cross-tenant provisioning is 14.2's system
    path). Re-applying the same template is a 201 no-op (``created=false``); a different one is a
    409 industry.template_conflict."""
    if INDUSTRY_TEMPLATE_APPLY not in current.permissions:
        raise PermissionDeniedError(
            code="rbac.permission_denied",
            message=f"Missing permission: {INDUSTRY_TEMPLATE_APPLY}",
            details={"permission": INDUSTRY_TEMPLATE_APPLY},
        )
    if tenant_id != current.tenant_id:
        # D-007 isolation: a tenant admin cannot provision another tenant. Reported as a permission
        # denial (not a 404) so cross-tenant existence is not probeable.
        raise PermissionDeniedError(
            code="rbac.tenant_mismatch",
            message="Cannot apply a template to another tenant",
            details={"tenant_id": str(tenant_id)},
        )
    already = await queries.get_applied_template(session, tenant_id)

    async def _work() -> None:
        await loader.apply_template(session, tenant_id, template)

    await run_in_uow(session, _work)
    return ApplyResult(
        tenant_id=tenant_id, template_name=template, created=already != template
    )


@onboarding_router.post(
    "/tenants",
    response_model=OnboardTenantResponse,
    status_code=201,
    dependencies=[Depends(require_permission(ONBOARDING_TENANT_CREATE))],
)
async def onboard_tenant(
    payload: OnboardTenantRequest,
    session: SessionDep,
) -> OnboardTenantResponse:
    """Provision a whole tenant in ONE transaction (PLAN 14.2 / D-061): tenant + first admin user
    + the chosen industry template's COA/tax/currencies/UoMs/numbering/terminology. Guarded by
    ``onboarding.tenant.create`` (a platform action). Idempotent by slug: an already-taken slug is
    a 409 ``onboarding.slug_taken``; an unknown template is a 404. The whole flow runs through
    ``run_in_uow`` so any failure rolls the tenant + user + every slice back together."""
    result: onboarding.OnboardingResult | None = None

    async def _work() -> None:
        nonlocal result
        result = await onboarding.onboard_tenant(
            session,
            company_name=payload.company_name,
            slug=payload.slug,
            template_name=payload.template_name,
            admin_email=payload.admin_email,
            admin_password=payload.admin_password,
        )

    await run_in_uow(session, _work)
    assert result is not None  # run_in_uow only returns after _work committed
    return OnboardTenantResponse(
        tenant_id=result.tenant_id,
        slug=result.slug,
        admin_user_id=result.admin_user_id,
        template_applied=result.template_applied,
        instantiated=result.instantiated,
    )
