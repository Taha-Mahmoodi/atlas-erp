"""D-016 typed custom fields: the core registry + validate_custom_fields, against the real
session/db on the migrated template (D-025 — real commits work).

Covers the registry CRUD (create/ensure idempotent get-or-create/list ordering/soft-deactivate)
and the validator: unknown keys rejected, required enforced (with default fallback), per-type
coercion (STRING/NUMBER/BOOL/DATE) and the D-015 no-float rules for DECIMAL (string in/out, float
rejected) — the report builder + forms read defs through list_field_defs and gate payloads through
validate_custom_fields.
"""


import pytest

from app.core.custom_fields import (
    CustomFieldDef,
    create_field_def,
    deactivate_field_def,
    ensure_field_def,
    list_field_defs,
    validate_custom_fields,
)
from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import system_context

ENTITY = "inventory.item"


async def _def(
    session, tenant_id, field_key, data_type, *, required=False, default=None, label="L"
) -> CustomFieldDef:
    with system_context():
        d = await create_field_def(
            session,
            tenant_id,
            entity_key=ENTITY,
            field_key=field_key,
            label=label,
            data_type=data_type,
            is_required=required,
            default_value=default,
        )
        await session.commit()
    return d


# --- registry CRUD ------------------------------------------------------------


async def test_create_field_def_persists_and_lists_ordered(db_session, tenant_a):
    await _def(db_session, tenant_a, "warranty_months", "NUMBER")
    await _def(db_session, tenant_a, "barcode", "STRING")
    with system_context():
        defs = await list_field_defs(db_session, tenant_a, ENTITY)
    # Ordered by field_key for stable forms/reports (D-016).
    assert [d.field_key for d in defs] == ["barcode", "warranty_months"]


async def test_create_field_def_rejects_invalid_field_key(db_session, tenant_a):
    with system_context(), pytest.raises(ValidationFailedError) as exc:
        await create_field_def(
            db_session,
            tenant_a,
            entity_key=ENTITY,
            field_key="Bad Key",
            label="x",
            data_type="STRING",
        )
    assert exc.value.code == "custom_fields.invalid_field_key"


async def test_duplicate_field_def_raises_conflict(db_session, tenant_a):
    await _def(db_session, tenant_a, "barcode", "STRING")
    with system_context(), pytest.raises(ConflictError):
        await create_field_def(
            db_session,
            tenant_a,
            entity_key=ENTITY,
            field_key="barcode",
            label="x",
            data_type="STRING",
        )


async def test_ensure_field_def_is_idempotent(db_session, tenant_a):
    with system_context():
        first = await ensure_field_def(
            db_session, tenant_a, entity_key=ENTITY, field_key="barcode",
            label="Barcode", data_type="STRING",
        )
        second = await ensure_field_def(
            db_session, tenant_a, entity_key=ENTITY, field_key="barcode",
            label="Different label", data_type="STRING",
        )
        await db_session.commit()
    # The second call returns the EXISTING row unchanged — no duplicate, label not overwritten.
    assert first.id == second.id
    assert second.label == "Barcode"


async def test_deactivate_excludes_from_active_defs(db_session, tenant_a):
    await _def(db_session, tenant_a, "barcode", "STRING")
    with system_context():
        await deactivate_field_def(db_session, tenant_a, ENTITY, "barcode")
        await db_session.commit()
        active = await list_field_defs(db_session, tenant_a, ENTITY, active_only=True)
        every = await list_field_defs(db_session, tenant_a, ENTITY, active_only=False)
    assert active == []  # soft-deactivated, never hard-deleted
    assert [d.field_key for d in every] == ["barcode"]


# --- validate_custom_fields ---------------------------------------------------


async def test_validate_rejects_unknown_keys(db_session, tenant_a):
    await _def(db_session, tenant_a, "barcode", "STRING")
    with system_context():
        defs = await list_field_defs(db_session, tenant_a, ENTITY)
    with pytest.raises(ValidationFailedError) as exc:
        validate_custom_fields(defs, {"barcode": "X", "ghost": 1})
    assert exc.value.code == "custom_fields.unknown_keys"
    assert exc.value.details["keys"] == ["ghost"]


async def test_validate_enforces_required(db_session, tenant_a):
    await _def(db_session, tenant_a, "barcode", "STRING", required=True)
    with system_context():
        defs = await list_field_defs(db_session, tenant_a, ENTITY)
    with pytest.raises(ValidationFailedError) as exc:
        validate_custom_fields(defs, {})
    assert exc.value.code == "custom_fields.required"


async def test_validate_required_uses_default_when_absent(db_session, tenant_a):
    await _def(db_session, tenant_a, "rate", "DECIMAL", required=True, default="10")
    with system_context():
        defs = await list_field_defs(db_session, tenant_a, ENTITY)
    assert validate_custom_fields(defs, {}) == {"rate": "10"}


async def test_validate_coerces_each_type(db_session, tenant_a):
    await _def(db_session, tenant_a, "barcode", "STRING")
    await _def(db_session, tenant_a, "warranty_months", "NUMBER")
    await _def(db_session, tenant_a, "is_hazmat", "BOOL")
    await _def(db_session, tenant_a, "expires_on", "DATE")
    with system_context():
        defs = await list_field_defs(db_session, tenant_a, ENTITY)
    result = validate_custom_fields(
        defs,
        {
            "barcode": 12345,  # coerced to str
            "warranty_months": 24,
            "is_hazmat": True,
            "expires_on": "2026-12-31",
        },
    )
    assert result == {
        "barcode": "12345",
        "warranty_months": 24,
        "is_hazmat": True,
        "expires_on": "2026-12-31",
    }


async def test_validate_decimal_is_string_and_rejects_float(db_session, tenant_a):
    await _def(db_session, tenant_a, "rate", "DECIMAL")
    with system_context():
        defs = await list_field_defs(db_session, tenant_a, ENTITY)
    # DECIMAL arrives + leaves as a STRING (D-015 no-float), parsed exactly.
    assert validate_custom_fields(defs, {"rate": "19.95"}) == {"rate": "19.95"}
    # A JSON float is rejected outright.
    with pytest.raises(ValidationFailedError) as exc:
        validate_custom_fields(defs, {"rate": 19.95})
    assert exc.value.code == "custom_fields.type_mismatch"


async def test_validate_rejects_nested_value(db_session, tenant_a):
    await _def(db_session, tenant_a, "barcode", "STRING")
    with system_context():
        defs = await list_field_defs(db_session, tenant_a, ENTITY)
    with pytest.raises(ValidationFailedError) as exc:
        validate_custom_fields(defs, {"barcode": {"nested": 1}})
    assert exc.value.code == "custom_fields.not_scalar"


async def test_validate_number_rejects_bool(db_session, tenant_a):
    await _def(db_session, tenant_a, "warranty_months", "NUMBER")
    with system_context():
        defs = await list_field_defs(db_session, tenant_a, ENTITY)
    # A bool is an int subclass; it must NOT silently store as a NUMBER.
    with pytest.raises(ValidationFailedError):
        validate_custom_fields(defs, {"warranty_months": True})


async def test_defs_are_tenant_scoped(db_session, tenant_a, tenant_b):
    await _def(db_session, tenant_a, "barcode", "STRING")
    with system_context():
        defs_b = await list_field_defs(db_session, tenant_b, ENTITY)
    assert defs_b == []  # tenant B sees none of tenant A's defs
