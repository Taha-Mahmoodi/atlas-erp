"""Equipment service behaviour (PLAN 9.2, D-051): CRUD, the user-supplied unique code, the optional
finance cost-centre validation (D-029), and the status transitions.

Equipment goes through the REAL service under the tenant context (D-025), so tenancy stamping +
audit fire as in production.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.maintenance import service
from app.modules.maintenance.constants import EquipmentStatus
from app.modules.maintenance.schemas import EquipmentCreate, EquipmentUpdate
from tests.modules.maintenance.factories import build_cost_center, build_equipment


async def test_create_equipment_defaults_active(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A created piece of equipment is ACTIVE by default with its fields persisted."""
    with tenant_context(tenant_a):
        equipment = await service.create_equipment(
            db_session,
            tenant_a,
            EquipmentCreate(code="EQ-1", name="Pump", location="Plant A"),
        )
    assert equipment.status == EquipmentStatus.ACTIVE.value
    assert equipment.code == "EQ-1"
    assert equipment.location == "Plant A"


async def test_duplicate_code_conflicts(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A second piece of equipment with the same code in a tenant is a 409."""
    await build_equipment(db_session, tenant_a, code="EQ-DUP")
    with pytest.raises(ConflictError) as exc, tenant_context(tenant_a):
        await service.create_equipment(
            db_session, tenant_a, EquipmentCreate(code="EQ-DUP", name="Second")
        )
    assert exc.value.code == "maintenance.equipment_code_conflict"


async def test_cost_center_must_exist(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A supplied cost-centre id that does not exist in finance is a 422 (D-029)."""
    with pytest.raises(ValidationFailedError) as exc, tenant_context(tenant_a):
        await service.create_equipment(
            db_session,
            tenant_a,
            EquipmentCreate(code="EQ-CC", name="Press", cost_center_id=uuid.uuid4()),
        )
    assert exc.value.code == "maintenance.cost_center_not_found"


async def test_valid_cost_center_accepted(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A real finance cost-centre id is accepted and stored (D-029)."""
    cost_center_id = await build_cost_center(db_session, tenant_a)
    equipment = await build_equipment(
        db_session, tenant_a, code="EQ-CC2", cost_center_id=cost_center_id
    )
    assert equipment.cost_center_id == cost_center_id


async def test_update_equipment_status_and_fields(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A partial update mutates only the set fields; the status enum is stored as its string."""
    equipment = await build_equipment(db_session, tenant_a, code="EQ-UPD")
    with tenant_context(tenant_a):
        updated = await service.update_equipment(
            db_session,
            tenant_a,
            equipment.id,
            EquipmentUpdate(status=EquipmentStatus.RETIRED, notes="Decommissioned"),
        )
    assert updated.status == EquipmentStatus.RETIRED.value
    assert updated.notes == "Decommissioned"
    assert updated.code == "EQ-UPD"  # unchanged


async def test_update_revalidates_cost_center(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A changed cost-centre id on update is re-validated against finance (D-029)."""
    equipment = await build_equipment(db_session, tenant_a, code="EQ-RV")
    with pytest.raises(ValidationFailedError) as exc, tenant_context(tenant_a):
        await service.update_equipment(
            db_session,
            tenant_a,
            equipment.id,
            EquipmentUpdate(cost_center_id=uuid.uuid4()),
        )
    assert exc.value.code == "maintenance.cost_center_not_found"


async def test_get_unknown_equipment_404(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with pytest.raises(NotFoundError) as exc, tenant_context(tenant_a):
        await service.get_equipment(db_session, tenant_a, uuid.uuid4())
    assert exc.value.code == "maintenance.equipment_not_found"
