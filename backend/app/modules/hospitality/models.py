"""Hospitality models (PLAN 19 + Phase 21): the stored menu-availability row, the order-ticket
document, and the table-reservation trio (settings, the pacing counter, the reservation document).

SIX tables in ONE file — STRUCTURE §3 splits a module into a ``models/`` package only past ~600
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
from datetime import date, datetime, time
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
    DEFAULT_BOOKING_HORIZON_DAYS,
    DEFAULT_COVERS_MAX,
    DEFAULT_MAX_PARTY,
    DEFAULT_MIN_PARTY,
    DEFAULT_PARTIES_MAX,
    DEFAULT_SERVICE_CLOSE,
    DEFAULT_SERVICE_OPEN,
    AvailabilitySource,
    AvailabilityState,
    OrderTicketStatus,
    ReservationStatus,
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
    # The third moment worth stamping, and the only one that carries a REASON: cancelling is the
    # one terminal state a human chooses for a reason the numbers do not record anywhere else
    # (wrong table, party walked). Required by the service, so the pair is always written together.
    cancelled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
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


class ReservationSettings(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """The property's pacing configuration — AT MOST ONE ROW PER TENANT (Phase 21, spec Q3).

    A row of OVERRIDES, exactly like ``MenuAvailability`` next door: a tenant that never writes one
    books against the ``constants.DEFAULT_*`` values, so a property can take its first reservation
    without being configured first. That is also what makes finding 3 work — the missing slot row
    means DEFAULT capacity, and the defaults have to come from somewhere that is allowed to be
    absent.

    The 15-minute slot width is deliberately NOT here: it is ``constants.SLOT_MINUTES``, because it
    is half the meaning of ``hsp_service_slots``'s unique key and a manager editing it would
    silently re-point every stored counter (``SLOT_MINUTES``' own comment).

    ``service_open``/``service_close`` are UTC times (``constants.DEFAULT_SERVICE_OPEN``): Atlas
    stores no per-tenant timezone, so a bare wall clock would be a number nothing could resolve to
    an instant. A close at or before the open means the service runs past midnight and the window
    rolls into the next day — a late bar is the ordinary case, not an error.

    AuditMixin, unlike the counter row below: capacity policy is a handful of writes in a property's
    life and each one is a manager deciding how much revenue the room may take, which is exactly the
    shape D-010 is for.
    """

    __tablename__ = "hsp_reservation_settings"
    __table_args__ = (
        # ONE row per tenant. Explicitly named: the D-022 convention keys on column 0 (tenant_id)
        # only, so this and tenant_unique() below would collide on the same generated name.
        sa.UniqueConstraint("tenant_id", name="uq_hsp_reservation_settings_one_per_tenant"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        sa.CheckConstraint(
            "default_covers_max >= 0 AND default_parties_max >= 0",
            name="ck_hsp_reservation_settings_defaults_non_negative",
        ),
        # A property that wants to stop taking bookings closes its slots (covers_max = 0); a party
        # range that cannot admit anybody is a typo, and one that admits a party of zero is a
        # booking for nobody holding a table.
        sa.CheckConstraint(
            "min_party > 0 AND max_party >= min_party",
            name="ck_hsp_reservation_settings_party_range_sane",
        ),
        sa.CheckConstraint(
            "booking_horizon_days > 0",
            name="ck_hsp_reservation_settings_horizon_positive",
        ),
    )

    service_open: Mapped[time] = mapped_column(
        sa.Time, nullable=False, default=DEFAULT_SERVICE_OPEN
    )
    service_close: Mapped[time] = mapped_column(
        sa.Time, nullable=False, default=DEFAULT_SERVICE_CLOSE
    )
    default_covers_max: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=DEFAULT_COVERS_MAX
    )
    default_parties_max: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=DEFAULT_PARTIES_MAX
    )
    min_party: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=DEFAULT_MIN_PARTY)
    max_party: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=DEFAULT_MAX_PARTY)
    booking_horizon_days: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=DEFAULT_BOOKING_HORIZON_DAYS
    )


class ServiceSlot(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """The PACING COUNTER: how many covers and parties one 15-minute slot has taken (spec Q3).

    This is the unit of availability, and the fact that it is not a table is the phase's central
    finding. OpenTable and Resy both cap covers per slot and leave the physical table a revisable
    soft assignment made by a human at seating — so a booking locks THIS row, not a table, and
    ``table_code`` stays the free text the order ticket already carries.

    MATERIALISED LAZILY, by the first booking's upsert-on-lock, and that is where this row's shape
    differs from Phase 20's room allotment: a missing row there legitimately reads "nothing on
    sale", while a missing row HERE means DEFAULT capacity. A restaurant's capacity is standing
    config, and pre-creating every slot of every future night would be the grid-maintenance trap Q3
    warns about, twice over (96 rows a day per property, forever, for nights nobody books).
    A row therefore exists only because somebody booked against the slot, or because a manager
    overrode it — including to ``covers_max = 0``, which is how a slot is CLOSED.

    ``covers_max``/``parties_max`` are a SNAPSHOT of the settings defaults taken at materialisation.
    A later settings change does not reach back into nights already being booked, which is the
    honest reading (the guests already holding those covers were promised that room) and the reason
    the manager override exists at all.

    Deliberately NOT ``AuditMixin`` — the ``MenuAvailability`` argument exactly: this row is written
    on every booking and every cancellation, so a before/after diff per write would charge the
    guest's request for a second insert and produce noise nobody reads. The RESERVATION is the
    audited document, and it is what a dispute is settled from.

    The two CHECK pairs are the DB backstop under the service's pre-flight refusal, the
    ``inv_stock_quants`` shape (D-020/D-036): the service refuses ``hospitality.slot_full`` BEFORE
    writing, and the CHECK is what fires if that check is ever bypassed. Portable on both engines
    (D-003) because they are plain CHECKs.
    """

    __tablename__ = "hsp_service_slots"
    __table_args__ = (
        # One counter per (service date, slot). Doubles as the index the grid read uses: the
        # leading (tenant_id, service_date) columns serve "this night's counters" from one scan,
        # so no second index is declared (PERFORMANCE §1).
        sa.UniqueConstraint(
            "tenant_id",
            "service_date",
            "slot_start",
            name="uq_hsp_service_slots_tenant_id_service_date_slot_start",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        sa.CheckConstraint(
            "covers_booked >= 0 AND covers_booked <= covers_max",
            name="ck_hsp_service_slots_covers_within_max",
        ),
        sa.CheckConstraint(
            "parties_booked >= 0 AND parties_booked <= parties_max",
            name="ck_hsp_service_slots_parties_within_max",
        ),
    )

    # The BUSINESS date the slot belongs to, not the calendar date of ``slot_start`` — a service
    # running past midnight stays on one date, the same reason ``OrderTicket.opened_date`` exists.
    service_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    # The slot's own instant (UTC). An instant rather than a wall-clock time because "has the slot
    # started yet" decides whether a cancellation gives capacity back, and Atlas has no per-tenant
    # timezone to resolve a wall clock against.
    slot_start: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    covers_booked: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    covers_max: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    parties_booked: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    parties_max: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class TableReservation(UuidPKMixin, TenantMixin, AuditMixin, DocumentMixin, TimestampMixin, Base):
    """A booked table (Phase 21) — a D-012 document, numbered ``RSV-2026-000001`` at creation.

    Numbered at creation for the ``OrderTicket`` reason: the guest is told a reference on the phone
    and the floor reads it off the book, so there is no draft phase to defer the claim to. Audited
    (D-010) because a reservation is a promise to a named guest that staff can move, cancel or mark
    no-show, and "who changed my booking" is exactly the question the audit log answers.

    ``guest_contact`` is ONE free-text field, not a parsed phone/email pair. The website has already
    authenticated its guest (Q1 boundary) and owns notification; Atlas stores what the floor needs
    to shout down the pass. Structuring it here would be a validation surface with no consumer.

    ``ticket_id`` is set at SEATING and is a real composite tenant FK, unlike ``item_id`` elsewhere
    in this module (which is an opaque cross-module id, D-029) — the ticket is this module's own
    table, so the FK costs nothing and rules out a dangling reference. The docflow edge written
    alongside it is what the chain viewer renders; the column is what the book's row reads back
    without a join.

    NO ``table_code``: which table a party sits at is decided by a human at seating and lives on the
    check they are seated onto. Phase 19 already litigated why that is free text and why a table
    master nothing references would be config for its own sake — pacing does not reference tables
    either, so this phase does not earn one.
    """

    __tablename__ = "hsp_table_reservations"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        # The seated party's check. Composite so a reservation can never point at another tenant's
        # ticket; nullable, and a NULL composite FK is simply not enforced (MATCH SIMPLE).
        tenant_fk("hsp_order_tickets", "ticket_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "reservation_number",
            name="uq_hsp_table_reservations_tenant_id_reservation_number",
        ),
        sa.CheckConstraint(
            "party_size > 0", name="ck_hsp_table_reservations_party_size_positive"
        ),
        # PERFORMANCE §1: the book is read as "this service's reservations, optionally in state X",
        # ordered by slot — (tenant, service_date, slot_start) serves the filter AND the sort from
        # one index, and its leading columns also serve a plain "tonight's book".
        sa.Index(
            "ix_hsp_table_reservations_tenant_id_service_date_slot_start",
            "tenant_id",
            "service_date",
            "slot_start",
        ),
        # PERFORMANCE §1 again: every FK column gets an index, no exceptions.
        sa.Index(
            "ix_hsp_table_reservations_tenant_id_ticket_id", "tenant_id", "ticket_id"
        ),
    )

    reservation_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=ReservationStatus.CONFIRMED.value,
        server_default="CONFIRMED",
    )
    service_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    slot_start: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    party_size: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    guest_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    guest_contact: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
