"""Maintenance-order service behaviour (PLAN 9.2, D-051): create corrective (DRAFT vs SCHEDULED),
the equipment-must-be-ACTIVE rule, the schedule → start → complete lifecycle with actual_cost
recorded (record-only, no GL), the MNT- numbering + document, and cancel.

Orders go through the REAL service under the tenant context (D-025).
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.maintenance import service
from app.modules.maintenance.constants import (
    EquipmentStatus,
    MaintenanceOrderStatus,
    MaintenanceOrderType,
)
from app.modules.maintenance.schemas import (
    CompleteOrderRequest,
    MaintenanceOrderCreate,
)
from tests.modules.maintenance.conftest import MaintenanceSetup
from tests.modules.maintenance.factories import build_corrective_order, build_equipment


async def test_create_corrective_draft_without_schedule(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A corrective order with no scheduled_date is DRAFT, CORRECTIVE, with an MNT- number."""
    setup = maintenance_setup
    with tenant_context(setup.tenant_id):
        order = await service.create_corrective(
            db_session,
            setup.tenant_id,
            MaintenanceOrderCreate(equipment_id=setup.equipment_id, description="Fix leak"),
        )
    assert order.status == MaintenanceOrderStatus.DRAFT.value
    assert order.order_type == MaintenanceOrderType.CORRECTIVE.value
    assert order.maintenance_plan_id is None
    assert order.order_number.startswith("MNT")


async def test_create_corrective_scheduled_with_date(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A corrective order created WITH a scheduled_date is born SCHEDULED."""
    setup = maintenance_setup
    order = await build_corrective_order(
        db_session,
        setup.tenant_id,
        equipment_id=setup.equipment_id,
        scheduled_date=date(2026, 7, 1),
    )
    assert order.status == MaintenanceOrderStatus.SCHEDULED.value
    assert order.scheduled_date == date(2026, 7, 1)


async def test_order_against_inactive_equipment_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A corrective order can only target ACTIVE equipment — an INACTIVE unit is a 422."""
    equipment = await build_equipment(
        db_session, tenant_a, code="EQ-OFF", status=EquipmentStatus.INACTIVE
    )
    with pytest.raises(ValidationFailedError) as exc, tenant_context(tenant_a):
        await service.create_corrective(
            db_session,
            tenant_a,
            MaintenanceOrderCreate(equipment_id=equipment.id, description="Nope"),
        )
    assert exc.value.code == "maintenance.equipment_not_active"


async def test_full_lifecycle_schedule_start_complete(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """DRAFT → schedule → SCHEDULED → start → IN_PROGRESS → complete → COMPLETED, with actual_cost +
    completed_date recorded (record-only, D-051)."""
    setup = maintenance_setup
    order = await build_corrective_order(
        db_session, setup.tenant_id, equipment_id=setup.equipment_id
    )
    assert order.status == MaintenanceOrderStatus.DRAFT.value

    with tenant_context(setup.tenant_id):
        scheduled = await service.schedule_order(
            db_session, setup.tenant_id, order.id, date(2026, 8, 1)
        )
        assert scheduled.status == MaintenanceOrderStatus.SCHEDULED.value
        assert scheduled.scheduled_date == date(2026, 8, 1)

        started = await service.start_order(db_session, setup.tenant_id, order.id)
        assert started.status == MaintenanceOrderStatus.IN_PROGRESS.value

        completed = await service.complete_order(
            db_session,
            setup.tenant_id,
            order.id,
            CompleteOrderRequest(
                actual_cost=Decimal("125.50"), completed_date=date(2026, 8, 2)
            ),
        )
    assert completed.status == MaintenanceOrderStatus.COMPLETED.value
    assert Decimal(str(completed.actual_cost)) == Decimal("125.50")
    assert completed.completed_date == date(2026, 8, 2)


async def test_complete_without_date_defaults_today(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """Completing without a date stamps today; an IN_PROGRESS order need not be started first (a
    SCHEDULED order completes directly)."""
    setup = maintenance_setup
    order = await build_corrective_order(
        db_session,
        setup.tenant_id,
        equipment_id=setup.equipment_id,
        scheduled_date=date(2026, 9, 1),
    )
    with tenant_context(setup.tenant_id):
        completed = await service.complete_order(
            db_session, setup.tenant_id, order.id, CompleteOrderRequest()
        )
    assert completed.status == MaintenanceOrderStatus.COMPLETED.value
    assert completed.completed_date == date.today()


async def test_cannot_start_draft_order(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A DRAFT order must be scheduled before it can be started (409)."""
    setup = maintenance_setup
    order = await build_corrective_order(
        db_session, setup.tenant_id, equipment_id=setup.equipment_id
    )
    with pytest.raises(ConflictError) as exc, tenant_context(setup.tenant_id):
        await service.start_order(db_session, setup.tenant_id, order.id)
    assert exc.value.code == "maintenance.order_not_startable"


async def test_cannot_complete_draft_order(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A DRAFT order cannot be completed (409)."""
    setup = maintenance_setup
    order = await build_corrective_order(
        db_session, setup.tenant_id, equipment_id=setup.equipment_id
    )
    with pytest.raises(ConflictError) as exc, tenant_context(setup.tenant_id):
        await service.complete_order(
            db_session, setup.tenant_id, order.id, CompleteOrderRequest()
        )
    assert exc.value.code == "maintenance.order_not_completable"


async def test_cancel_order_and_terminal_immutable(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A non-terminal order cancels; a cancelled order is terminal and cannot be cancelled again."""
    setup = maintenance_setup
    order = await build_corrective_order(
        db_session, setup.tenant_id, equipment_id=setup.equipment_id
    )
    with tenant_context(setup.tenant_id):
        cancelled = await service.cancel_order(db_session, setup.tenant_id, order.id)
        assert cancelled.status == MaintenanceOrderStatus.CANCELLED.value
        with pytest.raises(ConflictError) as exc:
            await service.cancel_order(db_session, setup.tenant_id, order.id)
    assert exc.value.code == "maintenance.order_not_cancellable"


async def test_completed_order_cannot_be_cancelled(
    db_session: AsyncSession, maintenance_setup: MaintenanceSetup
) -> None:
    """A COMPLETED order is terminal — cancel is a 409."""
    setup = maintenance_setup
    order = await build_corrective_order(
        db_session,
        setup.tenant_id,
        equipment_id=setup.equipment_id,
        scheduled_date=date(2026, 10, 1),
    )
    with tenant_context(setup.tenant_id):
        await service.complete_order(
            db_session, setup.tenant_id, order.id, CompleteOrderRequest()
        )
        with pytest.raises(ConflictError) as exc:
            await service.cancel_order(db_session, setup.tenant_id, order.id)
    assert exc.value.code == "maintenance.order_not_cancellable"
