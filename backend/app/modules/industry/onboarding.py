"""Tenant onboarding orchestration (PLAN 14.2 / D-061): company info -> industry template ->
tenant + first admin user + the whole industry configuration, in ONE transaction.

Lives in the industry module, not admin, because it ORCHESTRATES both: it calls the admin
provisioning service (provision_tenant / provision_user / grant_admin_role) AND the industry
loader (apply_template). industry already imports admin.models, so industry -> admin is the
legal direction (STRUCTURE §5); admin importing industry would be a cycle. Each provisioning call
enters ``system_context`` itself (D-007 sanctioned site 2: the admin service + the loader wrap
their own writes); this orchestrator runs them all inside the caller's ``run_in_uow`` (D-011), so
tenant + admin role + admin user + every template slice either all commit together or all roll
back — a half-provisioned tenant can never persist.

Idempotency anchor is the tenant slug (D-061): if a tenant with the slug already exists we raise
ConflictError (409) rather than provisioning a duplicate — no onboarding-record table is needed.
"""

import uuid
from dataclasses import dataclass

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
from app.modules.industry.constants import ONBOARDING_TENANT_CREATE
from app.modules.industry.loader import apply_template, load_template

# Keys the first admin of a new tenant does NOT get (#165). Provisioning a WHOLE tenant is a
# platform action, not a tenant-admin one (constants.py says so at the key's declaration), so
# handing it to every tenant admin would let any tenant spin up arbitrary tenants. Everything
# else in the catalog is tenant-scoped and the tenant's own admin is entitled to it.
_PLATFORM_ONLY_KEYS = frozenset({ONBOARDING_TENANT_CREATE})


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


async def onboard_tenant(
    session: AsyncSession,
    *,
    company_name: str,
    slug: str,
    template_name: str,
    admin_email: str,
    admin_password: str,
) -> OnboardingResult:
    """Provision a whole tenant in one transaction (D-061): create the tenant, its Administrator
    role + first admin user, then apply the chosen industry template (COA, tax, currencies, UoMs,
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
    # Sync BEFORE granting: create_role validates every key against core_permissions, so a key
    # that no deploy has ever synced is un-grantable. Idempotent and cheap (one SELECT of the
    # keys, inserts only what is missing) — onboarding runs once per tenant, not per request.
    with system_context():
        await sync_permission_catalog(session)
    # The first admin gets the whole catalog minus the platform-only keys (#165). Deliberately a
    # computed set, not a curated list: a curated "tenant admin" subset is a second catalog that
    # rots the next time a module ships a permission, which is precisely how the first admin ended
    # up unable to read its own template's chart of accounts.
    await grant_admin_role(
        session,
        tenant.id,
        admin.id,
        token_version=admin.token_version,
        permission_keys=sorted(catalog_keys() - _PLATFORM_ONLY_KEYS),
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
