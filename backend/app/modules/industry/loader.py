"""Industry template loader (PLAN 14.1 / D-060): read + validate + idempotently apply a template.

The headline differentiator (Atlas's answer to SAP industry solutions): a tenant picks one of the
five shipped templates at onboarding and this loader instantiates its whole configuration —
COA preset, tax codes, currencies, UoMs, item categories, typed custom fields, approval presets,
module toggles, terminology overrides and numbering formats — in ONE transaction.

Two entry points:

* ``load_template(name)`` — read ``industry-templates/{name}.yaml``, validate the raw dict against
  ``industry-templates/_schema.yaml`` (the declarative single source of truth, D-060), then parse
  it into a typed :class:`IndustryTemplate`. Pure + side-effect-free; cached per process (the files
  are shipped, immutable at runtime). The router and the tests call it directly.

* ``apply_template(session, tenant_id, name)`` — the idempotent provisioning path. Runs under
  ``system_context`` (provisioning, D-007) inside the caller's ``run_in_uow`` (D-011). It:
    1. resolves the existing :class:`TenantIndustryConfig` — if the SAME template is already
       applied it is a NO-OP (returns the row); a DIFFERENT one raises ConflictError (a tenant's
       industry is chosen once, D-060);
    2. records the config row;
    3. applies the CORE/ADMIN-owned slices DIRECTLY (industry may import core + admin): custom-field
       defs (core/custom_fields, idempotent get-or-create), numbering sequences (core/numbering,
       idempotent ensure), terminology + module-toggle TenantSettings (admin table, upserted);
    4. PUBLISHES :class:`IndustryTemplateApplying` carrying the validated template — finance,
       inventory and procurement each create THEIR slice idempotently in the same transaction via
       their provisioning handlers (the §5-clean seam: industry NEVER imports their services).

The whole apply is one unit of work: any handler failure rolls the WHOLE thing back (D-011), so a
half-applied template can never persist.
"""

import functools
import uuid
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.custom_fields import ensure_field_def
from app.core.events import publish
from app.core.exceptions import ConflictError, NotFoundError
from app.core.models import JSON_VARIANT  # noqa: F401 - documents the TenantSetting value type
from app.core.numbering import ensure_sequence
from app.core.tenancy import system_context
from app.modules.admin.models import TenantSetting
from app.modules.industry.constants import (
    MODULE_TOGGLES_SETTING_KEY,
    SHIPPED_TEMPLATES,
    TERMINOLOGY_SETTING_KEY,
)
from app.modules.industry.events import IndustryTemplateApplying
from app.modules.industry.schema_validator import IndustrySchemaError, validate_against_schema
from app.modules.industry.schemas import IndustryTemplate

# industry-templates/ is a TOP-LEVEL repo dir (STRUCTURE §1), four parents up from this file
# (industry -> modules -> app -> backend -> repo-root).
TEMPLATES_DIR = Path(__file__).resolve().parents[4] / "industry-templates"
SCHEMA_PATH = TEMPLATES_DIR / "_schema.yaml"


@functools.cache
def _load_schema() -> dict[str, Any]:
    """The parsed _schema.yaml (the JSON-Schema). Cached: it is a shipped file, immutable at
    runtime."""
    return yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))


@functools.cache
def load_template(name: str) -> IndustryTemplate:
    """Read, schema-validate and parse the shipped template ``name`` (D-060).

    Raises NotFoundError (404) if ``name`` is not a shipped template, IndustrySchemaError (422) if
    the YAML violates _schema.yaml, and a Pydantic ValidationError if the typed parse fails (a
    build error — caught by test_templates_valid). Cached per process; the files are immutable at
    runtime."""
    if name not in SHIPPED_TEMPLATES:
        raise NotFoundError(
            message=f"Unknown industry template {name!r}",
            code="industry.template_not_found",
            details={"name": name, "shipped": list(SHIPPED_TEMPLATES)},
        )
    raw = yaml.safe_load((TEMPLATES_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
    validate_against_schema(raw, _load_schema())
    if raw.get("name") != name:
        # The schema enum permits any shipped name; this enforces file-stem == declared name so a
        # mis-named file (a copy-paste hazard) is caught, not silently applied as the wrong one.
        raise IndustrySchemaError(
            "/name", f"declared name {raw.get('name')!r} != file stem {name!r}"
        )
    return IndustryTemplate.model_validate(raw)


async def get_applied_config(session: AsyncSession, tenant_id: uuid.UUID):
    """The tenant's TenantIndustryConfig row, or None. The loader's idempotency anchor; also
    re-exported via queries for the UI."""
    # Local import: models import is module-internal; keeping it here avoids a top-level cycle with
    # the events module which imports schemas (no cycle in practice, but this keeps loader's
    # top-level imports to core/admin only, documenting the §5 boundary).
    from app.modules.industry.models import TenantIndustryConfig

    with system_context():
        stmt = select(TenantIndustryConfig).where(
            TenantIndustryConfig.tenant_id == tenant_id
        )
        return (await session.execute(stmt)).scalar_one_or_none()


async def _upsert_setting(
    session: AsyncSession, tenant_id: uuid.UUID, key: str, value: Any
) -> None:
    """Idempotent upsert of one admin TenantSetting under system_context. The terminology overrides
    and module toggles are admin-owned settings the loader writes directly (D-060: the simplest
    §5-clean option — admin owns Tenant/TenantSetting and industry may import admin models). Mutates
    an existing row so re-apply updates in place (and audit captures the diff)."""
    with system_context():
        existing = (
            await session.execute(
                select(TenantSetting).where(
                    TenantSetting.tenant_id == tenant_id, TenantSetting.key == key
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.value = value
        else:
            session.add(TenantSetting(tenant_id=tenant_id, key=key, value=value))
        await session.flush()


async def _apply_core_slices(
    session: AsyncSession, tenant_id: uuid.UUID, template: IndustryTemplate
) -> None:
    """Apply the CORE/ADMIN-owned slices the loader owns directly (D-060): custom-field defs,
    numbering sequences, terminology + module-toggle settings. All idempotent (get-or-create /
    upsert) so re-applying the same template never duplicates. Each slice runs under
    ``system_context`` (provisioning) — the defs/sequences/settings are tenant-scoped reads+writes
    that stamp tenant_id explicitly (D-007)."""
    with system_context():
        for field in template.custom_fields:
            await ensure_field_def(
                session,
                tenant_id,
                entity_key=field.entity_key,
                field_key=field.field_key,
                label=field.label,
                data_type=field.type,
                is_required=field.required,
                default_value=field.default,
            )
        for sequence_name, fmt in template.numbering_formats.items():
            await ensure_sequence(
                session,
                tenant_id,
                sequence_name,
                fmt.prefix,
                fmt.padding,
                fmt.year_reset,
            )
    await _upsert_setting(session, tenant_id, TERMINOLOGY_SETTING_KEY, dict(template.terminology))
    await _upsert_setting(session, tenant_id, MODULE_TOGGLES_SETTING_KEY, dict(template.modules))


async def apply_template(
    session: AsyncSession, tenant_id: uuid.UUID, name: str
) -> "object":
    """Idempotently apply industry template ``name`` to ``tenant_id`` (D-060).

    Call inside ``run_in_uow`` (the router/onboarding do): this records the config + applies the
    core/admin slices + publishes IndustryTemplateApplying; the finance/inventory/procurement
    handlers create their slices when run_in_uow drains the event before commit, so the whole apply
    is ONE transaction.

    Idempotency: re-applying the SAME template is a no-op (returns the existing config unchanged —
    the core slices' get-or-create + the handlers' skip-if-exists make the second pass harmless);
    applying a DIFFERENT template raises ConflictError (a tenant's industry is chosen once, D-060).
    Returns the TenantIndustryConfig row."""
    from app.modules.industry.models import TenantIndustryConfig

    template = load_template(name)
    existing = await get_applied_config(session, tenant_id)
    if existing is not None and existing.template_name != name:
        raise ConflictError(
            message=(
                f"Tenant already has industry template {existing.template_name!r}; "
                f"cannot switch to {name!r}"
            ),
            code="industry.template_conflict",
            details={"current": existing.template_name, "requested": name},
        )
    if existing is None:
        with system_context():
            config = TenantIndustryConfig(tenant_id=tenant_id, template_name=name)
            session.add(config)
            await session.flush()
    else:
        config = existing

    await _apply_core_slices(session, tenant_id, template)
    publish(session, IndustryTemplateApplying(tenant_id=tenant_id, template=template))
    return config
