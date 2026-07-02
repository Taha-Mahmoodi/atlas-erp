"""Production-order request/response schemas (Pydantic v2, ApiModel base) for PLAN 8.2.

A production order is a header (``ProductionOrder``) + its exploded components + routing-snapshot
operations. Create takes the parent item + quantity + warehouse (+ optional BOM/routing/dates); the
service explodes the active BOM into the component reservations and snapshots the routing — the
component + operation rows are SERVER-DERIVED, not posted by the client. Issue + finish are action
endpoints with their own request bodies. ``status`` is server-driven (DRAFT at create, advanced by
the release/issue/finish actions), so it is absent from Create. Quantities/costs are ``Decimal``
strings (D-015); the detail nests the components + operations.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from app.core.schemas import ApiModel
from app.modules.manufacturing.constants import ProductionOrderStatus


class ProductionOrderCreate(ApiModel):
    """Create a production order (D-048), born DRAFT + exploded. ``item_id`` is the opaque inventory
    PARENT item to produce; ``quantity`` (> 0) is how many. ``warehouse_id`` is where components are
    issued from and finished goods land. ``bom_id`` is OPTIONAL — the service resolves the item's
    ACTIVE default BOM when omitted (422 ``manufacturing.no_active_bom`` if none). ``routing_id`` is
    OPTIONAL — the active routing is snapshotted when omitted (a routingless order is allowed). The
    planned dates are optional scheduling hints (8.3 uses them)."""

    item_id: uuid.UUID
    quantity: Decimal
    warehouse_id: uuid.UUID
    bom_id: uuid.UUID | None = None
    routing_id: uuid.UUID | None = None
    planned_start_date: date | None = None
    planned_end_date: date | None = None
    notes: str | None = None


class ProductionOrderComponentRead(ApiModel):
    id: uuid.UUID
    production_order_id: uuid.UUID
    line_number: int
    component_item_id: uuid.UUID
    required_quantity: Decimal
    issued_quantity: Decimal
    uom_id: uuid.UUID
    bin_id: uuid.UUID


class ProductionOrderOperationRead(ApiModel):
    id: uuid.UUID
    production_order_id: uuid.UUID
    operation_number: int
    work_center_id: uuid.UUID
    description: str | None
    setup_time_minutes: Decimal
    run_time_minutes_per_unit: Decimal
    planned_minutes: Decimal


class ProductionOrderRead(ApiModel):
    id: uuid.UUID
    order_number: str
    status: ProductionOrderStatus
    item_id: uuid.UUID
    quantity: Decimal
    bom_id: uuid.UUID
    routing_id: uuid.UUID | None
    warehouse_id: uuid.UUID
    planned_start_date: date | None
    planned_end_date: date | None
    finished_quantity: Decimal
    accumulated_wip_cost: Decimal
    notes: str | None
    released_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProductionOrderDetail(ProductionOrderRead):
    """The header plus its exploded components and routing-snapshot operations (the GET {id} +
    create/issue/finish response). The nested rows are server-derived."""

    components: list[ProductionOrderComponentRead]
    operations: list[ProductionOrderOperationRead]


class ProductionOrderFilter(ApiModel):
    """List filters. None means "no constraint"; folded into the cursor's filter fingerprint so a
    cursor cannot cross filtered views."""

    item_id: uuid.UUID | None = None
    status: ProductionOrderStatus | None = None


class ComponentIssueLine(ApiModel):
    """One component line to issue (D-048). ``component_line_number`` names the order's component
    row; ``quantity`` is how much to issue (must not push issued past required, v1 over-issue
    policy); ``bin_id`` OVERRIDES the component's default source bin when set; optional lot/serial
    codes name the existing instance the stock leaves on (resolved to ids by the service)."""

    component_line_number: int
    quantity: Decimal
    bin_id: uuid.UUID | None = None
    lot_code: str | None = None
    serial_code: str | None = None


class IssueComponentsRequest(ApiModel):
    """Issue components to a production order (D-048). When ``lines`` is omitted/empty the service
    issues EACH component's full remaining required_quantity from its default bin ("issue all
    required"); otherwise only the named lines are issued at the given quantities/bins. The move
    date defaults to today; a date in a CLOSED period rolls the whole issue back."""

    lines: list[ComponentIssueLine] | None = None
    move_date: date | None = None


class FinishOrderRequest(ApiModel):
    """Finish a production order to stock (D-048). ``finished_quantity`` (> 0) is how many parent
    units are completed (must not exceed the remaining ordered quantity); ``finished_bin_id`` is
    where they land. Optional lot/serial codes create the finished instance master on the receipt.
    The move date defaults to today; a CLOSED period rolls the whole finish back."""

    finished_quantity: Decimal
    finished_bin_id: uuid.UUID
    lot_code: str | None = None
    serial_code: str | None = None
    move_date: date | None = None
