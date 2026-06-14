"""Position service tests (PLAN 10.1, D-052): CRUD, code uniqueness, department validation.

Driven through the real service under the tenant context (D-025).
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.hr import service
from app.modules.hr.schemas import PositionCreate, PositionUpdate
from tests.modules.hr.factories import build_department, build_position


async def test_create_and_get_position(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    dept = await build_department(db_session, tenant_a, code="DEP-POS")
    position = await build_position(
        db_session, tenant_a, code="POS-1", title="Engineer", department_id=dept.id
    )
    with tenant_context(tenant_a):
        got = await service.get_position(db_session, tenant_a, position.id)
    assert got.code == "POS-1"
    assert got.title == "Engineer"
    assert got.department_id == dept.id


async def test_duplicate_code_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    await build_position(db_session, tenant_a, code="POS-DUP")
    with tenant_context(tenant_a), pytest.raises(ConflictError):
        await service.create_position(
            db_session, tenant_a, PositionCreate(code="POS-DUP", title="Dup")
        )


async def test_unknown_department_rejected(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.create_position(
            db_session,
            tenant_a,
            PositionCreate(code="POS-BAD", title="Bad dept", department_id=uuid.uuid4()),
        )
    assert exc.value.code == "hr.department_not_found"


async def test_unassigned_position_allowed(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    """A position need not belong to a department (nullable department_id)."""
    position = await build_position(db_session, tenant_a, code="POS-FREE", department_id=None)
    assert position.department_id is None


async def test_update_position_fields(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    dept = await build_department(db_session, tenant_a, code="DEP-PU")
    position = await build_position(db_session, tenant_a, code="POS-UPD")
    with tenant_context(tenant_a):
        updated = await service.update_position(
            db_session,
            tenant_a,
            position.id,
            PositionUpdate(title="Senior Engineer", department_id=dept.id, is_active=False),
        )
    assert updated.title == "Senior Engineer"
    assert updated.department_id == dept.id
    assert updated.is_active is False


async def test_update_to_unknown_department_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    position = await build_position(db_session, tenant_a, code="POS-UB")
    with tenant_context(tenant_a), pytest.raises(ValidationFailedError) as exc:
        await service.update_position(
            db_session,
            tenant_a,
            position.id,
            PositionUpdate(department_id=uuid.uuid4()),
        )
    assert exc.value.code == "hr.department_not_found"


async def test_get_missing_position_raises(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await service.get_position(db_session, tenant_a, uuid.uuid4())
