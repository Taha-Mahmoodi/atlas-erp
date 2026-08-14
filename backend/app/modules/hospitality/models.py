"""Hospitality models (PLAN 19): the stored menu-availability row and the order-ticket document.

THREE tables in ONE file — STRUCTURE §3 splits a module into a ``models/`` package only past ~600
lines, and these do not reach it.

CROSS-MODULE IDS ARE OPAQUE (D-029/STRUCTURE §5). ``item_id`` is an inventory ``Item`` id carried
as a plain column with NO FK into ``inv_items``; existence is validated through
``inventory/queries.item_exists`` at write time, the manufacturing-BOM precedent. A menu item IS
an ordinary inventory item — Phase 19 adds no second item entity and no recipe entity.

NO ``currency_code`` COLUMN, on the ticket or its lines. A property's checks are all denominated in
the tenant's functional currency (D-019, finance owns it); the ticket never trades FX and never
posts a journal of its own, so a snapshot column would be a value that never varies — the same
reason inventory moves and manufacturing production orders carry none. Task 7 labels the wire
amount from ``finance/queries.functional_currency``. If Phase 20's folio ever settles a check in a
second currency, that is an ALTER with a real requirement behind it.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.docflow import DocumentMixin, document_fk
from app.core.models import (
    AuditMixin,
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import MoneyType, QuantityType
from app.modules.hospitality.constants import (
    AvailabilitySource,
    AvailabilityState,
    OrderTicketStatus,
)


class MenuAvailability(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One row per sellable item: what the guest read path is allowed to say about it (spec Q2).

    ``item_id`` is UNIQUE per tenant — one stored answer per dish, so the read is a single indexed
    ``IN`` lookup no matter how big the menu is (Q2: a derived answer costs ~1,080 queries for a
    60-item menu, 360x over PERFORMANCE §2's ≤3). An item with NO row is AVAILABLE; the table only
    ever holds overrides, so it stays menu-sized rather than growing with service.

    ``available_until`` time-boxes an 86 (Lightspeed's snooze). It is evaluated LAZILY, on read —
    Atlas has no scheduler and Phase 19 does not add one, so an expired row simply stops counting
    the next time anybody looks. Nothing sweeps expired rows: the next ``set_availability`` for
    that item overwrites in place, which is what bounds the table.

    Deliberately NOT ``AuditMixin`` (D-010), unlike almost every other master row in Atlas. That is
    the whole reason this table exists instead of a flag on ``Item``: 86-ing is shift-scoped churn
    a kitchen flips dozens of times a night, and a before/after audit row per flip would be noise
    charged to every write. ``source`` records human-vs-countdown, which is the only part of the
    provenance anyone reads back.

    Timestamps still matter: ``updated_at`` is what ``collection_etag``'s ``MAX(updated_at)``
    aggregates over, so a countdown flipping a dish to 86 must move it or the website keeps
    serving a 304 for a sold-out dish — the exact failure Q2 rejects derivation for. This is why
    availability is written by loading and mutating the row (the ORM applies ``onupdate``), never
    by a bulk ``update()`` statement.
    """

    __tablename__ = "hsp_menu_availability"
    __table_args__ = (
        # One stored answer per sellable item. Doubles as the index the batched read path uses:
        # (tenant_id, item_id) leading columns serve `tenant_id = ? AND item_id IN (...)`, so no
        # second index is declared (PERFORMANCE §1).
        sa.UniqueConstraint(
            "tenant_id", "item_id", name="uq_hsp_menu_availability_tenant_id_item_id"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        sa.CheckConstraint(
            "remaining_qty IS NULL OR remaining_qty >= 0",
            name="ck_hsp_menu_availability_remaining_non_negative",
        ),
    )

    # OPAQUE inventory item id (D-029): validated via inventory/queries, never a FK into inv_*.
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    state: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=AvailabilityState.AVAILABLE.value,
        server_default="AVAILABLE",
    )
    # Portions left on a LIMITED countdown; NULL for every other state (there is nothing to count).
    remaining_qty: Mapped[Decimal | None] = mapped_column(QuantityType(), nullable=True)
    # End of a time-boxed 86; NULL means "until somebody clears it". Evaluated lazily on read.
    available_until: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    source: Mapped[str] = mapped_column(
        sa.String(10),
        nullable=False,
        default=AvailabilitySource.MANUAL.value,
        server_default="MANUAL",
    )


class OrderTicket(UuidPKMixin, TenantMixin, AuditMixin, DocumentMixin, TimestampMixin, Base):
    """The CHECK for one table (PLAN 19 Task 4) — a D-012 document, not a scratch row.

    ``ticket_number`` is the gapless ``TKT-`` number claimed AT CREATION (the sales-order /
    goods-receipt branch): a ticket is referenceable by the kitchen, the guest and Phase 20.6's
    folio the moment the server opens it, so there is no draft phase to defer numbering to.
    ``status`` runs the strictly-sequential ``OrderTicketStatus`` lifecycle.

    ``fired_at`` / ``settled_at`` stamp the two moments that carry effects: fire is when the
    ingredients are committed (Q4 — depletion hangs off it, off-request) and settle is when the
    money is. Both are nullable because both are ahead of a live ticket.

    ``opened_date`` is the service date. It is what the number claim year-resets on and what the
    floor's "today's checks" list filters by — a DATE rather than a read over ``created_at``,
    because a service running past midnight must stay on one date and comparing a timestamp column
    to a calendar day is exactly where that breaks. (A restaurant "business date" that formally
    closes at the night audit is Phase 20's concern; this is the ordinary calendar date until then.)

    ``total_amount`` is MAINTAINED as Σ line_amount, never recomputed on read — Q6 requires the
    order response to be authoritative over whatever price the website cached 60 seconds ago.

    Audited (D-010), unlike ``MenuAvailability`` deliberately next door: a ticket is written a
    handful of times in its life (open, fire, progress, settle) and carries money, which is exactly
    the shape AuditMixin is for. The 86 flag is the opposite shape — dozens of flips a night with
    no money on them — which is why it is a separate table with no audit at all.
    """

    __tablename__ = "hsp_order_tickets"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        sa.UniqueConstraint(
            "tenant_id", "ticket_number", name="uq_hsp_order_tickets_tenant_id_ticket_number"
        ),
        sa.CheckConstraint("total_amount >= 0", name="ck_hsp_order_tickets_total_non_negative"),
        sa.CheckConstraint(
            "guest_count IS NULL OR guest_count > 0",
            name="ck_hsp_order_tickets_guest_count_positive",
        ),
        # PERFORMANCE §1: the floor and the KDS both read "this service's checks in state X" —
        # (tenant, opened_date, status) serves that filtered, paginated list from one index, and
        # its leading columns also serve a plain "today's checks".
        sa.Index(
            "ix_hsp_order_tickets_tenant_id_opened_date_status",
            "tenant_id",
            "opened_date",
            "status",
        ),
    )

    ticket_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=OrderTicketStatus.OPEN.value,
        server_default="OPEN",
    )
    opened_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    # The floor location the check belongs to ("T12", "BAR-3"). Free text: table plans are property
    # -specific and a table master nothing else references would be config for its own sake.
    table_code: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    guest_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    fired_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(
        MoneyType(), nullable=False, default=Decimal(0), server_default="0"
    )
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


class OrderTicketLine(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """One ordered dish on a ticket (PLAN 19 Task 4).

    ``item_id`` is an OPAQUE inventory id (D-029) — the sellable menu item, which is an ordinary
    ``Item`` that is the parent of a recipe BOM. NOT AuditMixin (the header-line exclusion every
    other document in Atlas follows: the audited header carries the business state).

    NO ``uom_id``, unlike a sales-order line. A sales line needs one because a customer may order in
    BOX and be shipped in EA; a kitchen sells the dish in the unit it is costed in. ``quantity`` is
    therefore always in the item's BASE UoM, which is also the basis a recipe BOM explodes against —
    so Task 5's depletion needs no conversion step, and there is no unit for a caller to get wrong.

    ``unit_price`` is the price the check is struck at, SNAPSHOT on the line: a menu reprice
    tonight must not rewrite a check already open on a table. ``line_amount`` = quantity ×
    unit_price, maintained by the service and summed into the header's total.
    """

    __tablename__ = "hsp_order_ticket_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id",
            "ticket_id",
            "line_number",
            name="uq_hsp_order_ticket_lines_ticket_line",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hsp_order_tickets", "ticket_id"),
        sa.CheckConstraint("quantity > 0", name="ck_hsp_order_ticket_lines_quantity_positive"),
        sa.CheckConstraint(
            "unit_price >= 0", name="ck_hsp_order_ticket_lines_unit_price_non_negative"
        ),
        sa.CheckConstraint(
            "seat_number IS NULL OR seat_number > 0",
            name="ck_hsp_order_ticket_lines_seat_positive",
        ),
    )

    ticket_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    line_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # OPAQUE inventory item id (D-029): the sellable dish. No FK into inv_items.
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QuantityType(), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)
    line_amount: Mapped[Decimal] = mapped_column(MoneyType(), nullable=False)
    # Which seat ordered it — how a runner delivers the right plate to the right guest.
    seat_number: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    # The kitchen instruction ("no onion", "allergy: nuts").
    notes: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
