"""BOM business logic (PLAN 8.1, D-047): header + component CRUD, activate/deactivate.

Rules enforced here (the service owns them, CLAUDE.md rule 7):

- **Identity ``(item_id, version)``** — a duplicate (item, version) is a ConflictError before the DB
  UNIQUE would raise. The parent ``item_id`` and ``uom_id`` are OPAQUE inventory ids validated via
  ``inventory/queries`` (D-029); a component ``component_item_id``/``uom_id`` likewise.
- **No self-component** — a component item that IS the BOM's parent item is rejected. Deeper
  multi-level cycles (A→B→A) are an 8.3 explosion-time concern (visited set + depth cap), not
  enforceable on a single-level row.
- **DRAFT-editable, then ACTIVE-frozen (D-047)** — the header and its components may be changed only
  while the BOM is DRAFT. Once ACTIVE the recipe is frozen: corrections are a NEW version. Editing /
  adding / deleting a component on a non-DRAFT BOM is a ConflictError.
- **Single ACTIVE default per item** — activating a BOM makes it the item's default and demotes any
  previously-default ACTIVE version's ``is_default`` flag, so exactly one default-active version
  exists per item.

``from __future__ import annotations`` keeps ``Page[Bom]`` (the ORM model) a string at import.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.inventory import queries as inventory_queries
from app.modules.manufacturing.constants import BomStatus
from app.modules.manufacturing.models import Bom, BomComponent
from app.modules.manufacturing.schemas import BomComponentCreate, BomCreate, BomUpdate


async def _require_item(session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """The opaque inventory item must exist (D-029) — validated via inventory/queries."""
    if not await inventory_queries.item_exists(session, tenant_id, item_id):
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="manufacturing.item_not_found",
            details={"item_id": str(item_id)},
        )


async def _require_uom(session: AsyncSession, tenant_id: uuid.UUID, uom_id: uuid.UUID) -> None:
    """The opaque inventory UoM must exist (D-029) — validated via inventory/queries (a UoM is a
    distinct inventory entity from an item, so it has its own existence check)."""
    if not await inventory_queries.uom_exists(session, tenant_id, uom_id):
        raise ValidationFailedError(
            message="Referenced unit of measure does not exist",
            code="manufacturing.uom_not_found",
            details={"uom_id": str(uom_id)},
        )


async def get_bom(session: AsyncSession, tenant_id: uuid.UUID, bom_id: uuid.UUID) -> Bom:
    bom = await session.get(Bom, bom_id)
    if bom is None or bom.tenant_id != tenant_id:
        raise NotFoundError(message="BOM not found", code="manufacturing.bom_not_found")
    return bom


async def create_bom(session: AsyncSession, tenant_id: uuid.UUID, payload: BomCreate) -> Bom:
    """Create a BOM header (born DRAFT). Validates the parent item + UoM exist; rejects a duplicate
    (item, version)."""
    await _require_item(session, tenant_id, payload.item_id)
    await _require_uom(session, tenant_id, payload.uom_id)
    existing = (
        await session.execute(
            select(Bom.id).where(
                Bom.tenant_id == tenant_id,
                Bom.item_id == payload.item_id,
                Bom.version == payload.version,
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"A BOM for this item with version {payload.version} already exists",
            code="manufacturing.bom_version_conflict",
            details={"item_id": str(payload.item_id), "version": payload.version},
        )
    bom = Bom(
        tenant_id=tenant_id,
        item_id=payload.item_id,
        version=payload.version,
        name=payload.name,
        status=BomStatus.DRAFT.value,
        base_quantity=payload.base_quantity,
        uom_id=payload.uom_id,
        is_default=False,
        notes=payload.notes,
    )
    session.add(bom)
    await session.flush()
    return bom


async def update_bom(
    session: AsyncSession, tenant_id: uuid.UUID, bom_id: uuid.UUID, payload: BomUpdate
) -> Bom:
    """Partial update of a BOM header — only while DRAFT (D-047). ``item_id``/``version`` are
    immutable; a changed ``uom_id`` is re-validated. A non-DRAFT BOM is frozen (ConflictError)."""
    bom = await get_bom(session, tenant_id, bom_id)
    if bom.status != BomStatus.DRAFT.value:
        raise ConflictError(
            message="Only a DRAFT BOM can be edited; create a new version to change an active BOM",
            code="manufacturing.bom_not_draft",
            details={"status": bom.status},
        )
    data = payload.model_dump(exclude_unset=True)
    if data.get("uom_id") is not None:
        await _require_uom(session, tenant_id, data["uom_id"])
    for field, value in data.items():
        setattr(bom, field, value)
    await session.flush()
    return bom


async def list_boms(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID | None = None,
    status: BomStatus | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Bom]:
    """Keyset-paginated BOMs ordered by (item_id, version) (D-014). The item/status filters narrow
    the set (index-served by (tenant, item_id, status)) and fold into the cursor fingerprint."""
    stmt = select(Bom).where(Bom.tenant_id == tenant_id)
    if item_id is not None:
        stmt = stmt.where(Bom.item_id == item_id)
    if status is not None:
        stmt = stmt.where(Bom.status == status.value)
    fingerprint = filter_fingerprint(item_id, status)
    return await paginate(
        session,
        stmt,
        order_by=[
            OrderKey(Bom.item_id, SortDirection.ASC),
            OrderKey(Bom.version, SortDirection.ASC),
        ],
        pk=Bom.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


# --- Components ----------------------------------------------------------------


async def bom_components_for(
    session: AsyncSession, tenant_id: uuid.UUID, bom_id: uuid.UUID
) -> list[BomComponent]:
    """The components of a BOM, ordered by line_number (the read helper 8.2/8.3 + the nested list
    use). One indexed read by (tenant, bom_id)."""
    stmt = (
        select(BomComponent)
        .where(BomComponent.tenant_id == tenant_id, BomComponent.bom_id == bom_id)
        .order_by(BomComponent.line_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def add_component(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    bom_id: uuid.UUID,
    payload: BomComponentCreate,
) -> BomComponent:
    """Add a component to a DRAFT BOM (D-047). Validates the BOM is DRAFT, the component item + UoM
    exist, the component is not the parent item (no self-reference), and the line_number is free
    (appends the next line when omitted)."""
    bom = await get_bom(session, tenant_id, bom_id)
    if bom.status != BomStatus.DRAFT.value:
        raise ConflictError(
            message="Components can be changed only while the BOM is DRAFT",
            code="manufacturing.bom_not_draft",
            details={"status": bom.status},
        )
    if payload.component_item_id == bom.item_id:
        raise ValidationFailedError(
            message="A BOM component cannot be the BOM's own parent item",
            code="manufacturing.bom_self_component",
            details={"item_id": str(bom.item_id)},
        )
    await _require_item(session, tenant_id, payload.component_item_id)
    await _require_uom(session, tenant_id, payload.uom_id)
    line_number = payload.line_number
    if line_number is None:
        max_line = (
            await session.execute(
                select(func.coalesce(func.max(BomComponent.line_number), 0)).where(
                    BomComponent.tenant_id == tenant_id, BomComponent.bom_id == bom_id
                )
            )
        ).scalar_one()
        line_number = int(max_line) + 10
    else:
        clash = (
            await session.execute(
                select(BomComponent.id).where(
                    BomComponent.tenant_id == tenant_id,
                    BomComponent.bom_id == bom_id,
                    BomComponent.line_number == line_number,
                )
            )
        ).first()
        if clash is not None:
            raise ConflictError(
                message=f"Line number {line_number} already exists on this BOM",
                code="manufacturing.bom_line_conflict",
                details={"line_number": line_number},
            )
    component = BomComponent(
        tenant_id=tenant_id,
        bom_id=bom_id,
        line_number=line_number,
        component_item_id=payload.component_item_id,
        quantity_per=payload.quantity_per,
        uom_id=payload.uom_id,
        scrap_percent=payload.scrap_percent,
        notes=payload.notes,
    )
    session.add(component)
    await session.flush()
    return component


async def delete_component(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    bom_id: uuid.UUID,
    component_id: uuid.UUID,
) -> None:
    """Delete a component from a DRAFT BOM (D-047). A non-DRAFT BOM is frozen (ConflictError). The
    component must belong to the named BOM."""
    bom = await get_bom(session, tenant_id, bom_id)
    if bom.status != BomStatus.DRAFT.value:
        raise ConflictError(
            message="Components can be changed only while the BOM is DRAFT",
            code="manufacturing.bom_not_draft",
            details={"status": bom.status},
        )
    component = await session.get(BomComponent, component_id)
    if (
        component is None
        or component.tenant_id != tenant_id
        or component.bom_id != bom_id
    ):
        raise NotFoundError(
            message="BOM component not found", code="manufacturing.bom_component_not_found"
        )
    await session.delete(component)
    await session.flush()


# --- Activation ----------------------------------------------------------------


async def activate_bom(
    session: AsyncSession, tenant_id: uuid.UUID, bom_id: uuid.UUID
) -> Bom:
    """Activate a DRAFT BOM (D-047): it becomes the item's ACTIVE default and is frozen. Requires at
    least one component (an empty BOM produces nothing). Demotes the previously-default ACTIVE
    version's ``is_default`` flag so exactly one default-active version exists per item. Activating
    an already-ACTIVE BOM is idempotent; activating an INACTIVE BOM is a ConflictError (reactivation
    is a new version)."""
    bom = await get_bom(session, tenant_id, bom_id)
    if bom.status == BomStatus.ACTIVE.value:
        return bom
    if bom.status != BomStatus.DRAFT.value:
        raise ConflictError(
            message="Only a DRAFT BOM can be activated",
            code="manufacturing.bom_not_activatable",
            details={"status": bom.status},
        )
    components = await bom_components_for(session, tenant_id, bom_id)
    if not components:
        raise ValidationFailedError(
            message="A BOM must have at least one component before it can be activated",
            code="manufacturing.bom_no_components",
        )
    # Demote the current default-active version for this item (mutate the loaded object so the audit
    # diff is captured — D-010, never a bulk update).
    current_default = (
        await session.execute(
            select(Bom).where(
                Bom.tenant_id == tenant_id,
                Bom.item_id == bom.item_id,
                Bom.status == BomStatus.ACTIVE.value,
                Bom.is_default.is_(True),
                Bom.id != bom.id,
            )
        )
    ).scalar_one_or_none()
    if current_default is not None:
        current_default.is_default = False
    bom.status = BomStatus.ACTIVE.value
    bom.is_default = True
    await session.flush()
    return bom


async def deactivate_bom(
    session: AsyncSession, tenant_id: uuid.UUID, bom_id: uuid.UUID
) -> Bom:
    """Deactivate an ACTIVE BOM (D-047): it becomes INACTIVE and loses the default flag, so the item
    has no active default until another version is activated. Deactivating a non-ACTIVE BOM is a
    ConflictError."""
    bom = await get_bom(session, tenant_id, bom_id)
    if bom.status != BomStatus.ACTIVE.value:
        raise ConflictError(
            message="Only an ACTIVE BOM can be deactivated",
            code="manufacturing.bom_not_active",
            details={"status": bom.status},
        )
    bom.status = BomStatus.INACTIVE.value
    bom.is_default = False
    await session.flush()
    return bom
