"""BOM service tests (PLAN 8.1, D-047): header + component CRUD, validation, activation.

Covers: parent item must exist; component must exist + differ from the parent (no self-reference);
(item, version) uniqueness; DRAFT-editability (an ACTIVE BOM is frozen); activate requires a
component + makes the version the single ACTIVE default (demoting a prior default); deactivate.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.manufacturing import queries, service
from app.modules.manufacturing.constants import BomStatus
from app.modules.manufacturing.schemas import BomComponentCreate, BomCreate
from tests.modules.manufacturing.factories import build_bom, build_bom_component


async def test_create_bom_and_add_component(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    bom = await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id
    )
    assert bom.status == BomStatus.DRAFT.value
    assert bom.is_default is False
    component = await build_bom_component(
        db_session,
        s.tenant_id,
        bom.id,
        component_item_id=s.component_item_id,
        uom_id=s.ea_uom_id,
        quantity_per=Decimal(3),
    )
    assert component.line_number == 10  # first appended line
    assert component.quantity_per == Decimal(3)
    with tenant_context(s.tenant_id):
        components = await queries.bom_components(db_session, s.tenant_id, bom.id)
    assert [c.component_item_id for c in components] == [s.component_item_id]


async def test_parent_item_must_exist(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    with tenant_context(s.tenant_id), pytest.raises(ValidationFailedError) as excinfo:
        await service.create_bom(
            db_session,
            s.tenant_id,
            BomCreate(item_id=uuid.uuid4(), uom_id=s.ea_uom_id, version="1", name="X"),
        )
    assert excinfo.value.code == "manufacturing.item_not_found"


async def test_component_must_exist(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    bom = await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id
    )
    with tenant_context(s.tenant_id), pytest.raises(ValidationFailedError) as excinfo:
        await service.add_component(
            db_session,
            s.tenant_id,
            bom.id,
            BomComponentCreate(
                component_item_id=uuid.uuid4(), uom_id=s.ea_uom_id, quantity_per=Decimal(1)
            ),
        )
    assert excinfo.value.code == "manufacturing.item_not_found"


async def test_no_self_component(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    """A component whose item IS the BOM's parent is rejected (no direct self-reference, D-047)."""
    s = manufacturing_setup
    bom = await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id
    )
    with tenant_context(s.tenant_id), pytest.raises(ValidationFailedError) as excinfo:
        await service.add_component(
            db_session,
            s.tenant_id,
            bom.id,
            BomComponentCreate(
                component_item_id=s.parent_item_id, uom_id=s.ea_uom_id, quantity_per=Decimal(1)
            ),
        )
    assert excinfo.value.code == "manufacturing.bom_self_component"


async def test_quantity_per_must_be_positive(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    """quantity_per <= 0 is rejected — the DB CHECK backs the schema (a zero quantity is meaningless
    for a component)."""
    s = manufacturing_setup
    bom = await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id
    )
    with tenant_context(s.tenant_id), pytest.raises(IntegrityError):
        await service.add_component(
            db_session,
            s.tenant_id,
            bom.id,
            BomComponentCreate(
                component_item_id=s.component_item_id, uom_id=s.ea_uom_id, quantity_per=Decimal(0)
            ),
        )
        await db_session.flush()


async def test_version_uniqueness(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id, version="1"
    )
    with tenant_context(s.tenant_id), pytest.raises(ConflictError) as excinfo:
        await service.create_bom(
            db_session,
            s.tenant_id,
            BomCreate(item_id=s.parent_item_id, uom_id=s.ea_uom_id, version="1", name="dup"),
        )
    assert excinfo.value.code == "manufacturing.bom_version_conflict"


async def test_activate_requires_a_component(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    bom = await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id
    )
    with tenant_context(s.tenant_id), pytest.raises(ValidationFailedError) as excinfo:
        await service.activate_bom(db_session, s.tenant_id, bom.id)
    assert excinfo.value.code == "manufacturing.bom_no_components"


async def test_activate_sets_single_default(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    """Activating version 2 demotes version 1's default flag — exactly one ACTIVE default per item,
    and ``get_active_bom_for_item`` resolves the latest activated one (D-047)."""
    s = manufacturing_setup
    bom1 = await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id, version="1"
    )
    await build_bom_component(
        db_session, s.tenant_id, bom1.id, component_item_id=s.component_item_id, uom_id=s.ea_uom_id
    )
    bom2 = await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id, version="2"
    )
    await build_bom_component(
        db_session, s.tenant_id, bom2.id, component_item_id=s.component_item_id, uom_id=s.ea_uom_id
    )
    with tenant_context(s.tenant_id):
        await service.activate_bom(db_session, s.tenant_id, bom1.id)
        await db_session.commit()
        active1 = await queries.get_active_bom_for_item(
            db_session, s.tenant_id, s.parent_item_id
        )
        assert active1 is not None and active1.id == bom1.id

        await service.activate_bom(db_session, s.tenant_id, bom2.id)
        await db_session.commit()
        active2 = await queries.get_active_bom_for_item(
            db_session, s.tenant_id, s.parent_item_id
        )
        assert active2 is not None and active2.id == bom2.id
        demoted = await service.get_bom(db_session, s.tenant_id, bom1.id)
        assert demoted.status == BomStatus.ACTIVE.value
        assert demoted.is_default is False


async def test_active_bom_is_frozen(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    """Once ACTIVE, the header can't be edited and components can't be added/removed (D-047)."""
    s = manufacturing_setup
    bom = await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id
    )
    component = await build_bom_component(
        db_session, s.tenant_id, bom.id, component_item_id=s.component_item_id, uom_id=s.ea_uom_id
    )
    with tenant_context(s.tenant_id):
        await service.activate_bom(db_session, s.tenant_id, bom.id)
        await db_session.commit()
        with pytest.raises(ConflictError) as add_exc:
            await service.add_component(
                db_session,
                s.tenant_id,
                bom.id,
                BomComponentCreate(
                    component_item_id=s.component_item_id,
                    uom_id=s.ea_uom_id,
                    quantity_per=Decimal(1),
                ),
            )
        assert add_exc.value.code == "manufacturing.bom_not_draft"
        with pytest.raises(ConflictError):
            await service.delete_component(db_session, s.tenant_id, bom.id, component.id)


async def test_deactivate_clears_default(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    bom = await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id
    )
    await build_bom_component(
        db_session, s.tenant_id, bom.id, component_item_id=s.component_item_id, uom_id=s.ea_uom_id
    )
    with tenant_context(s.tenant_id):
        await service.activate_bom(db_session, s.tenant_id, bom.id)
        await db_session.commit()
        deactivated = await service.deactivate_bom(db_session, s.tenant_id, bom.id)
        await db_session.commit()
        assert deactivated.status == BomStatus.INACTIVE.value
        assert deactivated.is_default is False
        active = await queries.get_active_bom_for_item(
            db_session, s.tenant_id, s.parent_item_id
        )
        assert active is None


async def test_draft_bom_editable(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    bom = await build_bom(
        db_session, s.tenant_id, item_id=s.parent_item_id, uom_id=s.ea_uom_id
    )
    component = await build_bom_component(
        db_session, s.tenant_id, bom.id, component_item_id=s.component_item_id, uom_id=s.ea_uom_id
    )
    with tenant_context(s.tenant_id):
        await service.delete_component(db_session, s.tenant_id, bom.id, component.id)
        await db_session.commit()
        remaining = await queries.bom_components(db_session, s.tenant_id, bom.id)
    assert remaining == []


async def test_get_missing_bom_raises(
    db_session: AsyncSession, manufacturing_setup
) -> None:
    s = manufacturing_setup
    with tenant_context(s.tenant_id), pytest.raises(NotFoundError):
        await service.get_bom(db_session, s.tenant_id, uuid.uuid4())
