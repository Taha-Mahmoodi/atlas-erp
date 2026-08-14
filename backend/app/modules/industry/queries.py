"""Industry's cross-module read interface (STRUCTURE §5 / D-060).

Thin, stable read surface other modules + the onboarding UI (14.2) may import: which template a
tenant applied, the shipped catalog, and a tenant's terminology overrides (so the frontend renders
"Patient" instead of "Customer"). The industry module is near the TOP of the dependency order;
nothing finance/inventory imports from here (they react to the event instead), so this file stays a
leaf-ish read contract. Every function takes an explicit ``tenant_id`` and runs the tenant-scoped
read under ``system_context`` where the row is system/config data the loader wrote under it.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import system_context
from app.modules.admin.models import TenantSetting
from app.modules.industry.constants import SHIPPED_TEMPLATES, TERMINOLOGY_SETTING_KEY
from app.modules.industry.loader import load_template
from app.modules.industry.models import TenantIndustryConfig
from app.modules.industry.schemas import IndustryTemplate


def list_templates() -> list[IndustryTemplate]:
    """The shipped templates, parsed (D-060). Pure read off the bundled YAML files — used by
    the list endpoint to show each template's display_name/description summary."""
    return [load_template(name) for name in SHIPPED_TEMPLATES]


async def get_applied_template(
    session: AsyncSession, tenant_id: uuid.UUID
) -> str | None:
    """The template_name the tenant has applied, or None if no template applied yet (D-060)."""
    with system_context():
        stmt = select(TenantIndustryConfig.template_name).where(
            TenantIndustryConfig.tenant_id == tenant_id
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def terminology_for(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, str]:
    """The tenant's terminology overrides (canonical term -> display label), or {} if none set
    (D-060). Read off the admin TenantSetting the loader wrote; the UI uses it to relabel forms and
    grids (customer -> Patient) without changing any internal name (STRUCTURE §7 lock)."""
    with system_context():
        stmt = select(TenantSetting.value).where(
            TenantSetting.tenant_id == tenant_id,
            TenantSetting.key == TERMINOLOGY_SETTING_KEY,
        )
        value = (await session.execute(stmt)).scalar_one_or_none()
    return dict(value) if isinstance(value, dict) else {}
