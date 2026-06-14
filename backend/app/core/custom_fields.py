"""Typed custom fields (D-016): the core-owned registry + validator + JSON column helper.

A STRUCTURE §2 amendment: this flat core file is the platform-level home for tenant-defined
custom fields, so EVERY module (finance is the bottom of the import order) can validate a custom
payload without importing the industry module — the industry layer (PLAN 14.1) is the first
WRITER of defs, but the registry and validator are core so the dependency direction stays
modules -> core (D-016 ownership fix; the draft put this in modules/industry, an upward import).

Three pieces, exactly as D-016 prescribes:

* ``CustomFieldDef`` (``core_custom_field_defs``) — one registered field for an entity, e.g. a
  ``barcode`` STRING on ``inventory.item``. ``entity_key`` is the dotted module.entity string the
  owning module passes; ``field_key`` is a flat scalar key (``^[a-z][a-z0-9_]{0,49}$``).
  UNIQUE(tenant_id, entity_key, field_key). Soft-deactivation via ``is_active`` (never hard delete,
  so stored values are not orphaned).

* ``validate_custom_fields(defs, values) -> dict`` — validate a custom_fields payload against the
  registered defs for ONE entity: unknown keys rejected, required enforced, each value coerced per
  type. The portable-JSON rules (D-015/D-016): DATE as an ISO-8601 string, DECIMAL as a STRING
  parsed via ``Decimal`` (never a JSON float), NUMBER an int, BOOL a bool. Flat scalars only —
  a dict/list value is rejected. The result is a plain JSON-portable dict the owning service
  stores in its ``custom_fields`` column.

* ``custom_fields_column()`` — the ``JSON_VARIANT`` column (JSONB on PG, JSON elsewhere) an
  extensible entity opts into, NOT NULL defaulting to ``{}``. Custom fields are descriptive /
  reporting fields by design: they are invisible to DB constraints, so anything participating in a
  financial invariant must be a real column (rule recorded in docs/modules/industry.md).

The CRUD service functions (``create_field_def`` / ``list_field_defs`` / ``deactivate_field_def``)
are the sanctioned write path — the industry template loader and a future admin endpoint both call
them, keeping data ownership at the platform level while templates supply content.
"""

import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.models import (
    JSON_VARIANT,
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
)

# Flat scalar key: lowercase, starts with a letter, <=50 chars. The same shape STRUCTURE §7 uses
# for snake_case identifiers; enforced at def-create so report-builder JSON paths stay portable.
FIELD_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,49}$")
# entity_key is the dotted module.entity the owning module passes, e.g. "inventory.item".
ENTITY_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class CustomFieldType(StrEnum):
    """The value types a custom field may hold (D-016). Stored as the UPPER value on the def row;
    the validator coerces a payload value to the matching Python type (DECIMAL via string, never a
    JSON float — consistent with D-015's no-float rule)."""

    STRING = "STRING"
    NUMBER = "NUMBER"
    DECIMAL = "DECIMAL"
    BOOL = "BOOL"
    DATE = "DATE"


class CustomFieldDef(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """One registered custom field for an entity (D-016). The owning module reads the active defs
    for its ``entity_key`` and passes them to ``validate_custom_fields`` on create/update. Audited
    (D-010): the field registry is tenant configuration — adding/deactivating a field changes what
    a form and the report builder surface."""

    __tablename__ = "core_custom_field_defs"
    __table_args__ = (
        # Explicit uq name: the D-022 convention keys on column 0 (tenant_id) only and would
        # collide with any other UNIQUE on this table starting with tenant_id.
        sa.UniqueConstraint(
            "tenant_id",
            "entity_key",
            "field_key",
            name="uq_core_custom_field_defs_tenant_id_entity_key_field_key",
        ),
        tenant_fk("adm_tenants"),
        # The owning-module read path: "active defs for this entity" filters (tenant, entity_key).
        sa.Index(
            "ix_core_custom_field_defs_tenant_id_entity_key", "tenant_id", "entity_key"
        ),
    )

    entity_key: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    field_key: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    label: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # Stored as the CustomFieldType UPPER value (the core/finance no-sa.Enum convention).
    data_type: Mapped[str] = mapped_column(sa.String(10), nullable=False)
    is_required: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    # The default value, stored portably as a STRING (rendered the same as a payload value would be
    # — DECIMAL/DATE as strings) and applied by the validator when the key is absent.
    default_value: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)


def custom_fields_column() -> Mapped[dict[str, Any]]:
    """A NOT-NULL JSON_VARIANT column (JSONB on PG, JSON elsewhere) for an extensible entity's
    custom_fields, defaulting to ``{}`` (D-016). An entity opts in by declaring
    ``custom_fields: Mapped[dict[str, Any]] = custom_fields_column()`` — keys are flat top-level
    scalars only; the owning service is the validation gate via ``validate_custom_fields``."""
    return mapped_column(
        JSON_VARIANT,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'"),
    )


def _coerce_value(definition: CustomFieldDef, raw: Any) -> Any:
    """Coerce one payload value to the def's type, raising ValidationFailedError on mismatch.

    Flat scalars only — a dict/list is rejected outright (D-016: no nesting). DECIMAL is parsed
    from a STRING via ``Decimal`` and re-emitted as a string (never a JSON float, D-015); DATE is an
    ISO-8601 string validated and normalized; NUMBER is an int; BOOL a bool; STRING a str."""
    if isinstance(raw, (dict, list)):
        raise ValidationFailedError(
            message=f"Custom field '{definition.field_key}' must be a flat scalar value",
            code="custom_fields.not_scalar",
            details={"field": definition.field_key},
        )
    data_type = CustomFieldType(definition.data_type)
    try:
        if data_type is CustomFieldType.STRING:
            return str(raw)
        if data_type is CustomFieldType.NUMBER:
            # A bool is an int subclass; reject it so a NUMBER field never silently stores True.
            if isinstance(raw, bool):
                raise ValueError
            return int(raw)
        if data_type is CustomFieldType.DECIMAL:
            # DECIMAL MUST arrive as a string (D-015 no-float): a float is rejected, an int/str is
            # parsed exactly and re-emitted as the canonical string form.
            if isinstance(raw, float):
                raise ValueError
            return str(Decimal(str(raw)))
        if data_type is CustomFieldType.BOOL:
            if not isinstance(raw, bool):
                raise ValueError
            return raw
        if data_type is CustomFieldType.DATE:
            # Validate + normalize to ISO-8601; reject a non-string or a non-date string.
            return date.fromisoformat(str(raw)).isoformat()
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise ValidationFailedError(
            message=(
                f"Custom field '{definition.field_key}' is not a valid {data_type.value}"
            ),
            code="custom_fields.type_mismatch",
            details={"field": definition.field_key, "expected": data_type.value},
        ) from exc
    raise ValidationFailedError(  # pragma: no cover - exhaustive enum, defensive
        message=f"Unsupported custom field type {definition.data_type}",
        code="custom_fields.unsupported_type",
    )


def validate_custom_fields(
    defs: list[CustomFieldDef], values: dict[str, Any] | None
) -> dict[str, Any]:
    """Validate a ``custom_fields`` payload against an entity's registered defs (D-016).

    - Unknown keys (no active def) are REJECTED — a custom payload may only carry registered fields.
    - Each present value is coerced to its def's type (DECIMAL as string, DATE ISO, etc.).
    - A required field absent from the payload uses the def's ``default_value`` when set, or raises.
    - An optional field absent from the payload is simply omitted from the result.

    Returns a fresh JSON-portable dict the owning service stores. Only ACTIVE defs are considered —
    callers load defs via ``list_field_defs(..., active_only=True)``."""
    values = values or {}
    by_key = {definition.field_key: definition for definition in defs}
    unknown = sorted(set(values) - set(by_key))
    if unknown:
        raise ValidationFailedError(
            message="Unknown custom field(s)",
            code="custom_fields.unknown_keys",
            details={"keys": unknown},
        )
    result: dict[str, Any] = {}
    for key, definition in by_key.items():
        if key in values and values[key] is not None:
            result[key] = _coerce_value(definition, values[key])
        elif definition.default_value is not None:
            result[key] = _coerce_value(definition, definition.default_value)
        elif definition.is_required:
            raise ValidationFailedError(
                message=f"Custom field '{key}' is required",
                code="custom_fields.required",
                details={"field": key},
            )
    return result


# --- CRUD service (the sanctioned write path: industry loader + admin endpoint) ----------------


async def list_field_defs(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    entity_key: str,
    *,
    active_only: bool = True,
) -> list[CustomFieldDef]:
    """The active (or all) registered defs for an entity, ordered by field_key for stable forms
    and reports (D-016). Owning-module services call this with ``active_only=True`` to gate a
    payload."""
    stmt = select(CustomFieldDef).where(
        CustomFieldDef.tenant_id == tenant_id,
        CustomFieldDef.entity_key == entity_key,
    )
    if active_only:
        stmt = stmt.where(CustomFieldDef.is_active.is_(True))
    stmt = stmt.order_by(CustomFieldDef.field_key)
    return list((await session.execute(stmt)).scalars().all())


async def get_field_def(
    session: AsyncSession, tenant_id: uuid.UUID, entity_key: str, field_key: str
) -> CustomFieldDef | None:
    """One def by its natural key (tenant, entity_key, field_key); None if not registered. Used by
    the idempotent loader's get-or-create."""
    stmt = select(CustomFieldDef).where(
        CustomFieldDef.tenant_id == tenant_id,
        CustomFieldDef.entity_key == entity_key,
        CustomFieldDef.field_key == field_key,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_field_def(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    entity_key: str,
    field_key: str,
    label: str,
    data_type: str,
    is_required: bool = False,
    default_value: str | None = None,
) -> CustomFieldDef:
    """Register a custom field (D-016). Validates the entity_key / field_key shapes and the type,
    then inserts; a duplicate (tenant, entity_key, field_key) raises ConflictError (the DB UNIQUE
    backstops). The idempotent loader calls ``ensure_field_def`` instead, which get-or-creates."""
    if not ENTITY_KEY_PATTERN.match(entity_key):
        raise ValidationFailedError(
            message="entity_key must be a dotted module.entity string",
            code="custom_fields.invalid_entity_key",
            details={"entity_key": entity_key},
        )
    if not FIELD_KEY_PATTERN.match(field_key):
        raise ValidationFailedError(
            message="field_key must match ^[a-z][a-z0-9_]{0,49}$",
            code="custom_fields.invalid_field_key",
            details={"field_key": field_key},
        )
    # Validate the type up front so a bad data_type fails at registration, not at first payload.
    coerced_type = CustomFieldType(data_type)
    if await get_field_def(session, tenant_id, entity_key, field_key) is not None:
        raise ConflictError(
            message=f"Custom field '{field_key}' already exists for {entity_key}",
            code="custom_fields.duplicate",
            details={"entity_key": entity_key, "field_key": field_key},
        )
    definition = CustomFieldDef(
        tenant_id=tenant_id,
        entity_key=entity_key,
        field_key=field_key,
        label=label,
        data_type=coerced_type.value,
        is_required=is_required,
        default_value=default_value,
    )
    session.add(definition)
    await session.flush()
    return definition


async def ensure_field_def(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    entity_key: str,
    field_key: str,
    label: str,
    data_type: str,
    is_required: bool = False,
    default_value: str | None = None,
) -> CustomFieldDef:
    """Idempotent get-or-create for a custom field (D-016), used by the industry template loader so
    re-applying a template never duplicates a def. Returns the existing row UNCHANGED if the
    (tenant, entity_key, field_key) is already registered, otherwise creates it."""
    existing = await get_field_def(session, tenant_id, entity_key, field_key)
    if existing is not None:
        return existing
    return await create_field_def(
        session,
        tenant_id,
        entity_key=entity_key,
        field_key=field_key,
        label=label,
        data_type=data_type,
        is_required=is_required,
        default_value=default_value,
    )


async def deactivate_field_def(
    session: AsyncSession, tenant_id: uuid.UUID, entity_key: str, field_key: str
) -> CustomFieldDef:
    """Soft-deactivate a field (D-016: never hard delete — stored values must not be orphaned).
    Mutates the loaded object so the audit diff is captured (D-010)."""
    definition = await get_field_def(session, tenant_id, entity_key, field_key)
    if definition is None:
        raise ValidationFailedError(
            message=f"Custom field '{field_key}' is not registered for {entity_key}",
            code="custom_fields.not_found",
            details={"entity_key": entity_key, "field_key": field_key},
        )
    definition.is_active = False
    await session.flush()
    return definition
