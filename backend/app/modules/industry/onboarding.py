"""Tenant onboarding orchestration (PLAN 14.2 / D-061): company info -> industry template ->
tenant + first admin user + the whole industry configuration, in ONE transaction.

Lives in the industry module, not admin, because it ORCHESTRATES both: it calls the admin
provisioning service (provision_tenant / provision_user / grant_admin_role) AND the industry
loader (apply_template). industry already imports admin.models, so industry -> admin is the
legal direction (STRUCTURE §5); admin importing industry would be a cycle. Each provisioning call
enters ``system_context`` itself (D-007 sanctioned site 2: the admin service + the loader wrap
their own writes); the ONE such block this file opens is ``_sync_catalog``'s, and it filters
nothing away — ``Permission`` is global, not a ``TenantMixin`` — it is there because
``sync_permission_catalog``'s contract asks its callers for it. This orchestrator runs everything
inside the caller's ``run_in_uow`` (D-011), so tenant + admin role + admin user + every template
slice either all commit together or all roll back — a half-provisioned tenant can never persist.

Idempotency anchor is the tenant slug (D-061): if a tenant with the slug already exists we raise
ConflictError (409) rather than provisioning a duplicate — no onboarding-record table is needed.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context
from app.modules.admin.service import (
    find_tenant_by_slug,
    grant_admin_role,
    provision_tenant,
    provision_user,
)
from app.modules.hr.constants import HR_EMPLOYEE_READ_COMPENSATION, HR_PAYROLL_READ
from app.modules.industry.constants import ONBOARDING_TENANT_CREATE
from app.modules.industry.loader import apply_template, load_template

# Keys the tenant's first admin does NOT get by default (#165, D-075). Named ONE BY ONE rather than
# derived from a namespace rule: two of the three sit inside a namespace the Owner otherwise holds
# in full, so no rule over key names would catch them. This is a DEFAULT, not a wall — the Owner
# holds admin.role.manage, so a tenant that wants its owner to see pay grants the key deliberately,
# and that grant is audited. Every catalog key is classified against this set by
# tests/modules/industry/test_onboarding_grant.py, which fails on any key nobody has classified.
_WITHHELD_FROM_FIRST_ADMIN = frozenset(
    {
        # Provisioning a WHOLE tenant is a platform action, not a tenant-admin one (constants.py
        # says so at the key's declaration): handing it to every tenant admin would let any tenant
        # spin up arbitrary tenants.
        ONBOARDING_TENANT_CREATE,
        # The D-009 masking gate. This key alone unmasks base_salary, national_id, tax_id,
        # date_of_birth and bank_account (hr/schemas.py) and gates the compensation-WRITE endpoint.
        # CLAUDE.md architecture rule 4 makes that masking binding and hr/constants.py designs for
        # exactly the principal who manages employees but cannot see their pay — so a tenant's
        # first login cannot be the moment the masking silently comes off.
        HR_EMPLOYEE_READ_COMPENSATION,
        # The same pay through the other door: a payroll run's lines are per-employee gross/tax/net
        # (PayrollRunLineRead), unmasked, gated only by this key. Withholding the employee-level
        # key while granting this one would be theatre.
        HR_PAYROLL_READ,
    }
)


@dataclass(frozen=True)
class OnboardingResult:
    """What the wizard shows after provisioning: the new tenant + its first admin, which template
    was applied, and a small summary of what was instantiated (D-061). Counts come off the parsed
    template — the apply is 1:1 with it on a fresh tenant, so no extra count queries are needed."""

    tenant_id: uuid.UUID
    slug: str
    admin_user_id: uuid.UUID
    template_applied: str
    instantiated: dict[str, int]


async def _sync_catalog(session: AsyncSession) -> None:
    """Upsert the code-declared permission catalog before the grant (#165): ``create_role`` checks
    every key against ``core_permissions``, so a key no deploy ever synced is un-grantable — and
    outside ``seed.py`` nothing syncs it, so a migrated-but-unseeded deploy would 422 here.

    ``core_permissions`` is GLOBAL data and this is its only writer on a request path, so two
    onboardings on such a deploy can both SELECT a key as missing and both INSERT it. Same SAVEPOINT
    remedy as ``hospitality/service/availability`` (D-003 portable, unlike ON CONFLICT): the loser's
    IntegrityError can only arrive after the winner COMMITTED — the unique index made it wait — so
    re-running the sync finds a complete catalog and inserts nothing, and the savepoint kept the
    outer transaction (the whole tenant) alive instead of failing the provision."""
    savepoint = await session.begin_nested()
    try:
        with system_context():
            await sync_permission_catalog(session)
    except IntegrityError:
        await savepoint.rollback()
        with system_context():
            await sync_permission_catalog(session)


async def onboard_tenant(
    session: AsyncSession,
    *,
    company_name: str,
    slug: str,
    template_name: str,
    admin_email: str,
    admin_password: str,
) -> OnboardingResult:
    """Provision a whole tenant in one transaction (D-061): create the tenant, its Owner role +
    first admin user, then apply the chosen industry template (COA, tax, currencies, UoMs,
    numbering, terminology, module toggles) via the loader.

    Call inside ``run_in_uow`` (the router does): the loader publishes IndustryTemplateApplying and
    the finance/inventory/procurement provisioning handlers create their slices in the SAME
    transaction. Any failure rolls the whole thing back — no half-provisioned tenant persists.

    Idempotent by slug: an existing slug raises ConflictError (409). ``template_name`` is validated
    by ``load_template`` (404 for an unknown template) before any write. The functional currency
    comes from the template (each declares exactly one); add an override param when a caller needs
    one, not before.
    """
    existing = await find_tenant_by_slug(session, slug)
    if existing is not None:
        raise ConflictError(
            message=f"A tenant with slug {slug!r} already exists",
            code="onboarding.slug_taken",
            details={"slug": slug},
        )

    # Validate the template name up front (raises NotFoundError/404 for an unknown template) so a
    # bad name fails BEFORE any tenant/user row is created — the write path below only ever runs
    # for a known-good template. The parsed spec also feeds the instantiated summary.
    template = load_template(template_name)

    tenant = await provision_tenant(session, slug=slug, name=company_name)
    # provision_user hashes the plaintext with argon2id itself (D-008 single hashing path).
    admin = await provision_user(
        session, tenant.id, email=admin_email, password=admin_password
    )
    await _sync_catalog(session)
    # The Owner gets the whole catalog minus _WITHHELD_FROM_FIRST_ADMIN (#165, D-075). Deliberately
    # subtractive: a curated "tenant admin" subset is a second catalog that rots the next time a
    # module ships a permission, which is precisely how the first admin ended up unable to read its
    # own template's chart of accounts. Named "Owner", NOT "Administrator" — that name belongs to
    # grant_admin_role's six-key default (seed, the test factories), and two same-named is_system
    # roles differing 25x in power would be indistinguishable in the roles UI.
    await grant_admin_role(
        session,
        tenant.id,
        admin.id,
        token_version=admin.token_version,
        role_name="Owner",
        permission_keys=sorted(catalog_keys() - _WITHHELD_FROM_FIRST_ADMIN),
    )
    await apply_template(session, tenant.id, template_name)

    return OnboardingResult(
        tenant_id=tenant.id,
        slug=slug,
        admin_user_id=admin.id,
        template_applied=template_name,
        instantiated={
            "accounts": len(template.chart_of_accounts.accounts),
            "uoms": len(template.uoms),
            "tax_codes": len(template.tax_codes),
        },
    )
