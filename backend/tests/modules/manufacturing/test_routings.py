"""Routing service tests (PLAN 8.1, D-047): header + operation CRUD, validation, activation.

Covers: item must exist; work centre must exist; operation ordering (auto-appended multiples of 10);
times >= 0 (DB CHECK); (item, version) uniqueness; DRAFT-editability (an ACTIVE routing is frozen);
activate requires an operation + makes the version the single ACTIVE default; deactivate.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.manufacturing import queries, service
from app.modules.manufacturing.constants import RoutingStatus
from app.modules.manufacturing.schemas import RoutingCreate, RoutingOperationCreate
from tests.modules.manufacturing.factories import (
    build_routing,
    build_routing_operation,
    build_work_center,
)


async def test_create_routing_and_add_operations(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    wc = await build_work_center(db_session, s.tenant_id, code="WC-A")
    routing = await build_routing(db_session, s.tenant_id, item_id=s.parent_item_id)
    assert routing.status == RoutingStatus.DRAFT.value
    op1 = await build_routing_operation(
        db_session, s.tenant_id, routing.id, work_center_id=wc.id
    )
    op2 = await build_routing_operation(
        db_session, s.tenant_id, routing.id, work_center_id=wc.id
    )
    assert op1.operation_number == 10
    assert op2.operation_number == 20  # auto-appended ordering
    with tenant_context(s.tenant_id):
        operations = await queries.routing_operations(db_session, s.tenant_id, routing.id)
    assert [o.operation_number for o in operations] == [10, 20]


async def test_routing_item_must_exist(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    with tenant_context(s.tenant_id), pytest.raises(ValidationFailedError) as excinfo:
        await service.create_routing(
            db_session, s.tenant_id, RoutingCreate(item_id=uuid.uuid4(), version="1", name="X")
        )
    assert excinfo.value.code == "manufacturing.item_not_found"


async def test_operation_work_center_must_exist(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    routing = await build_routing(db_session, s.tenant_id, item_id=s.parent_item_id)
    with tenant_context(s.tenant_id), pytest.raises(ValidationFailedError) as excinfo:
        await service.add_operation(
            db_session,
            s.tenant_id,
            routing.id,
            RoutingOperationCreate(work_center_id=uuid.uuid4()),
        )
    assert excinfo.value.code == "manufacturing.work_center_not_found"


async def test_operation_times_must_be_non_negative(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    """A negative run time is rejected by the DB CHECK (the schema default is 0)."""
    s = manufacturing_setup
    wc = await build_work_center(db_session, s.tenant_id, code="WC-NEG")
    routing = await build_routing(db_session, s.tenant_id, item_id=s.parent_item_id)
    with tenant_context(s.tenant_id), pytest.raises(IntegrityError):
        await service.add_operation(
            db_session,
            s.tenant_id,
            routing.id,
            RoutingOperationCreate(
                work_center_id=wc.id, run_time_minutes_per_unit=Decimal(-1)
            ),
        )
        await db_session.flush()


async def test_routing_version_uniqueness(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    await build_routing(db_session, s.tenant_id, item_id=s.parent_item_id, version="1")
    with tenant_context(s.tenant_id), pytest.raises(ConflictError) as excinfo:
        await service.create_routing(
            db_session,
            s.tenant_id,
            RoutingCreate(item_id=s.parent_item_id, version="1", name="dup"),
        )
    assert excinfo.value.code == "manufacturing.routing_version_conflict"


async def test_duplicate_operation_number_conflicts(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    wc = await build_work_center(db_session, s.tenant_id, code="WC-OP")
    routing = await build_routing(db_session, s.tenant_id, item_id=s.parent_item_id)
    await build_routing_operation(
        db_session, s.tenant_id, routing.id, work_center_id=wc.id, operation_number=10
    )
    with tenant_context(s.tenant_id), pytest.raises(ConflictError) as excinfo:
        await service.add_operation(
            db_session,
            s.tenant_id,
            routing.id,
            RoutingOperationCreate(work_center_id=wc.id, operation_number=10),
        )
    assert excinfo.value.code == "manufacturing.routing_operation_conflict"


async def test_activate_requires_an_operation(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    routing = await build_routing(db_session, s.tenant_id, item_id=s.parent_item_id)
    with tenant_context(s.tenant_id), pytest.raises(ValidationFailedError) as excinfo:
        await service.activate_routing(db_session, s.tenant_id, routing.id)
    assert excinfo.value.code == "manufacturing.routing_no_operations"


async def test_activate_sets_single_default(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    wc = await build_work_center(db_session, s.tenant_id, code="WC-DEF")
    r1 = await build_routing(db_session, s.tenant_id, item_id=s.parent_item_id, version="1")
    await build_routing_operation(db_session, s.tenant_id, r1.id, work_center_id=wc.id)
    r2 = await build_routing(db_session, s.tenant_id, item_id=s.parent_item_id, version="2")
    await build_routing_operation(db_session, s.tenant_id, r2.id, work_center_id=wc.id)
    with tenant_context(s.tenant_id):
        await service.activate_routing(db_session, s.tenant_id, r1.id)
        await db_session.commit()
        await service.activate_routing(db_session, s.tenant_id, r2.id)
        await db_session.commit()
        active = await queries.get_active_routing_for_item(
            db_session, s.tenant_id, s.parent_item_id
        )
        assert active is not None and active.id == r2.id
        demoted = await service.get_routing(db_session, s.tenant_id, r1.id)
        assert demoted.is_default is False


async def test_active_routing_is_frozen(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    wc = await build_work_center(db_session, s.tenant_id, code="WC-FRZ")
    routing = await build_routing(db_session, s.tenant_id, item_id=s.parent_item_id)
    await build_routing_operation(db_session, s.tenant_id, routing.id, work_center_id=wc.id)
    with tenant_context(s.tenant_id):
        await service.activate_routing(db_session, s.tenant_id, routing.id)
        await db_session.commit()
        with pytest.raises(ConflictError) as excinfo:
            await service.add_operation(
                db_session,
                s.tenant_id,
                routing.id,
                RoutingOperationCreate(work_center_id=wc.id),
            )
        assert excinfo.value.code == "manufacturing.routing_not_draft"


async def test_deactivate_routing(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    wc = await build_work_center(db_session, s.tenant_id, code="WC-DEA")
    routing = await build_routing(db_session, s.tenant_id, item_id=s.parent_item_id)
    await build_routing_operation(db_session, s.tenant_id, routing.id, work_center_id=wc.id)
    with tenant_context(s.tenant_id):
        await service.activate_routing(db_session, s.tenant_id, routing.id)
        await db_session.commit()
        deactivated = await service.deactivate_routing(db_session, s.tenant_id, routing.id)
        await db_session.commit()
        assert deactivated.status == RoutingStatus.INACTIVE.value
        active = await queries.get_active_routing_for_item(
            db_session, s.tenant_id, s.parent_item_id
        )
        assert active is None


async def test_get_missing_routing_raises(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    with tenant_context(s.tenant_id), pytest.raises(NotFoundError):
        await service.get_routing(db_session, s.tenant_id, uuid.uuid4())
