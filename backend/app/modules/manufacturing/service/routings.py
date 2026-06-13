"""Routing business logic (PLAN 8.1, D-047): header + operation CRUD, activate/deactivate.

Mirrors the BOM service shape (D-047 gives BOM and routing the same identity + activation model):

- **Identity ``(item_id, version)``** — a duplicate is a ConflictError before the DB UNIQUE. The
  ``item_id`` is an OPAQUE inventory id validated via ``inventory/queries`` (D-029).
- **DRAFT-editable, then ACTIVE-frozen** — header + operations change only while DRAFT; an active
  routing is frozen (corrections are a new version).
- **Operations** reference a ``work_center_id`` that must exist in this tenant (an intra-module
  read); ``operation_number`` is unique per routing and the run order (appended as the next multiple
  of 10 when omitted). Setup/run times (minutes) are >= 0 (the schema defaults + the DB CHECK).
- **Single ACTIVE default per item** — activating demotes the previously-default ACTIVE version.

``from __future__ import annotations`` keeps ``Page[Routing]`` (the ORM model) a string at import.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.pagination import DEFAULT_LIMIT, OrderKey, SortDirection, filter_fingerprint, paginate
from app.core.schemas import Page
from app.modules.inventory import queries as inventory_queries
from app.modules.manufacturing.constants import RoutingStatus
from app.modules.manufacturing.models import Routing, RoutingOperation, WorkCenter
from app.modules.manufacturing.schemas import RoutingCreate, RoutingOperationCreate, RoutingUpdate


async def _require_item(session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """The opaque inventory item must exist (D-029) — validated via inventory/queries."""
    if not await inventory_queries.item_exists(session, tenant_id, item_id):
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="manufacturing.item_not_found",
            details={"item_id": str(item_id)},
        )


async def _require_work_center(
    session: AsyncSession, tenant_id: uuid.UUID, work_center_id: uuid.UUID
) -> None:
    """The work centre must exist in this tenant (an INTRA-module read — work centres live in
    manufacturing, so this is a direct existence check, not a cross-module query)."""
    found = (
        await session.execute(
            select(WorkCenter.id).where(
                WorkCenter.tenant_id == tenant_id, WorkCenter.id == work_center_id
            )
        )
    ).first()
    if found is None:
        raise ValidationFailedError(
            message="Referenced work centre does not exist",
            code="manufacturing.work_center_not_found",
            details={"work_center_id": str(work_center_id)},
        )


async def get_routing(
    session: AsyncSession, tenant_id: uuid.UUID, routing_id: uuid.UUID
) -> Routing:
    routing = await session.get(Routing, routing_id)
    if routing is None or routing.tenant_id != tenant_id:
        raise NotFoundError(
            message="Routing not found", code="manufacturing.routing_not_found"
        )
    return routing


async def create_routing(
    session: AsyncSession, tenant_id: uuid.UUID, payload: RoutingCreate
) -> Routing:
    """Create a routing header (born DRAFT). Validates the item exists; rejects a duplicate
    (item, version)."""
    await _require_item(session, tenant_id, payload.item_id)
    existing = (
        await session.execute(
            select(Routing.id).where(
                Routing.tenant_id == tenant_id,
                Routing.item_id == payload.item_id,
                Routing.version == payload.version,
            )
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            message=f"A routing for this item with version {payload.version} already exists",
            code="manufacturing.routing_version_conflict",
            details={"item_id": str(payload.item_id), "version": payload.version},
        )
    routing = Routing(
        tenant_id=tenant_id,
        item_id=payload.item_id,
        version=payload.version,
        name=payload.name,
        status=RoutingStatus.DRAFT.value,
        is_default=False,
        notes=payload.notes,
    )
    session.add(routing)
    await session.flush()
    return routing


async def update_routing(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    routing_id: uuid.UUID,
    payload: RoutingUpdate,
) -> Routing:
    """Partial update of a routing header — only while DRAFT (D-047). ``item_id``/``version`` are
    immutable. A non-DRAFT routing is frozen (ConflictError)."""
    routing = await get_routing(session, tenant_id, routing_id)
    if routing.status != RoutingStatus.DRAFT.value:
        raise ConflictError(
            message="Only a DRAFT routing can be edited; create a new version to change an active "
            "routing",
            code="manufacturing.routing_not_draft",
            details={"status": routing.status},
        )
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(routing, field, value)
    await session.flush()
    return routing


async def list_routings(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID | None = None,
    status: RoutingStatus | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Page[Routing]:
    """Keyset-paginated routings ordered by (item_id, version) (D-014). The item/status filters
    narrow the set (index-served by (tenant, item_id, status)) and fold into the cursor
    fingerprint."""
    stmt = select(Routing).where(Routing.tenant_id == tenant_id)
    if item_id is not None:
        stmt = stmt.where(Routing.item_id == item_id)
    if status is not None:
        stmt = stmt.where(Routing.status == status.value)
    fingerprint = filter_fingerprint(item_id, status)
    return await paginate(
        session,
        stmt,
        order_by=[
            OrderKey(Routing.item_id, SortDirection.ASC),
            OrderKey(Routing.version, SortDirection.ASC),
        ],
        pk=Routing.id,
        cursor=cursor,
        limit=limit,
        filters=fingerprint,
    )


# --- Operations ----------------------------------------------------------------


async def routing_operations_for(
    session: AsyncSession, tenant_id: uuid.UUID, routing_id: uuid.UUID
) -> list[RoutingOperation]:
    """The operations of a routing, ordered by operation_number (the read helper 8.2/8.3 + the
    nested list use). One indexed read by (tenant, routing_id)."""
    stmt = (
        select(RoutingOperation)
        .where(
            RoutingOperation.tenant_id == tenant_id,
            RoutingOperation.routing_id == routing_id,
        )
        .order_by(RoutingOperation.operation_number)
    )
    return list((await session.execute(stmt)).scalars().all())


async def add_operation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    routing_id: uuid.UUID,
    payload: RoutingOperationCreate,
) -> RoutingOperation:
    """Add an operation to a DRAFT routing (D-047). Validates the routing is DRAFT, the work centre
    exists, and the operation_number is free (appends the next multiple of 10 when omitted). Times
    >= 0 are guaranteed by the schema defaults + the DB CHECK."""
    routing = await get_routing(session, tenant_id, routing_id)
    if routing.status != RoutingStatus.DRAFT.value:
        raise ConflictError(
            message="Operations can be changed only while the routing is DRAFT",
            code="manufacturing.routing_not_draft",
            details={"status": routing.status},
        )
    await _require_work_center(session, tenant_id, payload.work_center_id)
    operation_number = payload.operation_number
    if operation_number is None:
        max_op = (
            await session.execute(
                select(func.coalesce(func.max(RoutingOperation.operation_number), 0)).where(
                    RoutingOperation.tenant_id == tenant_id,
                    RoutingOperation.routing_id == routing_id,
                )
            )
        ).scalar_one()
        operation_number = int(max_op) + 10
    else:
        clash = (
            await session.execute(
                select(RoutingOperation.id).where(
                    RoutingOperation.tenant_id == tenant_id,
                    RoutingOperation.routing_id == routing_id,
                    RoutingOperation.operation_number == operation_number,
                )
            )
        ).first()
        if clash is not None:
            raise ConflictError(
                message=f"Operation number {operation_number} already exists on this routing",
                code="manufacturing.routing_operation_conflict",
                details={"operation_number": operation_number},
            )
    operation = RoutingOperation(
        tenant_id=tenant_id,
        routing_id=routing_id,
        operation_number=operation_number,
        work_center_id=payload.work_center_id,
        description=payload.description,
        setup_time_minutes=payload.setup_time_minutes,
        run_time_minutes_per_unit=payload.run_time_minutes_per_unit,
        notes=payload.notes,
    )
    session.add(operation)
    await session.flush()
    return operation


async def delete_operation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    routing_id: uuid.UUID,
    operation_id: uuid.UUID,
) -> None:
    """Delete an operation from a DRAFT routing (D-047). A non-DRAFT routing is frozen
    (ConflictError). The operation must belong to the named routing."""
    routing = await get_routing(session, tenant_id, routing_id)
    if routing.status != RoutingStatus.DRAFT.value:
        raise ConflictError(
            message="Operations can be changed only while the routing is DRAFT",
            code="manufacturing.routing_not_draft",
            details={"status": routing.status},
        )
    operation = await session.get(RoutingOperation, operation_id)
    if (
        operation is None
        or operation.tenant_id != tenant_id
        or operation.routing_id != routing_id
    ):
        raise NotFoundError(
            message="Routing operation not found",
            code="manufacturing.routing_operation_not_found",
        )
    await session.delete(operation)
    await session.flush()


# --- Activation ----------------------------------------------------------------


async def activate_routing(
    session: AsyncSession, tenant_id: uuid.UUID, routing_id: uuid.UUID
) -> Routing:
    """Activate a DRAFT routing (D-047): it becomes the item's ACTIVE default and is frozen.
    Requires at least one operation. Demotes the previously-default ACTIVE version so exactly one
    default-active version exists per item. Already-ACTIVE is idempotent; INACTIVE is a
    ConflictError (reactivation is a new version)."""
    routing = await get_routing(session, tenant_id, routing_id)
    if routing.status == RoutingStatus.ACTIVE.value:
        return routing
    if routing.status != RoutingStatus.DRAFT.value:
        raise ConflictError(
            message="Only a DRAFT routing can be activated",
            code="manufacturing.routing_not_activatable",
            details={"status": routing.status},
        )
    operations = await routing_operations_for(session, tenant_id, routing_id)
    if not operations:
        raise ValidationFailedError(
            message="A routing must have at least one operation before it can be activated",
            code="manufacturing.routing_no_operations",
        )
    current_default = (
        await session.execute(
            select(Routing).where(
                Routing.tenant_id == tenant_id,
                Routing.item_id == routing.item_id,
                Routing.status == RoutingStatus.ACTIVE.value,
                Routing.is_default.is_(True),
                Routing.id != routing.id,
            )
        )
    ).scalar_one_or_none()
    if current_default is not None:
        current_default.is_default = False
    routing.status = RoutingStatus.ACTIVE.value
    routing.is_default = True
    await session.flush()
    return routing


async def deactivate_routing(
    session: AsyncSession, tenant_id: uuid.UUID, routing_id: uuid.UUID
) -> Routing:
    """Deactivate an ACTIVE routing (D-047): it becomes INACTIVE and loses the default flag.
    Deactivating a non-ACTIVE routing is a ConflictError."""
    routing = await get_routing(session, tenant_id, routing_id)
    if routing.status != RoutingStatus.ACTIVE.value:
        raise ConflictError(
            message="Only an ACTIVE routing can be deactivated",
            code="manufacturing.routing_not_active",
            details={"status": routing.status},
        )
    routing.status = RoutingStatus.INACTIVE.value
    routing.is_default = False
    await session.flush()
    return routing
