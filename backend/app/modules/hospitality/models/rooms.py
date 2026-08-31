"""The HOTEL side of hospitality (PLAN 20.1): what a property sells a night of, the physical rooms
it sells them from, the rate it sells them at, and the work order that makes a room sellable again.

Named ``rooms`` and not ``reservations`` for the reason ``table_reservations.py`` is named for its
tables: a restaurant booking holds a 15-minute pacing slot, a hotel booking holds a room-night
allotment, and the two share a word and nothing else. Phase 20 Task 4's booking document belongs
here too (or in a sibling if this file is near the §8.4 cap by then); it is a ROOM reservation and
must be named so that no reader has to guess which of the two a bare ``Reservation`` meant.

**Rooms sell by TYPE, not by room** (spec Q3). The guest buys "a double" and the physical room is
assigned at check-in, which is why ``RatePlan`` prices a room TYPE and ``Room`` carries no price at
all. The only thing a physical room decides is whether it can be sold at all, and that is
``housekeeping_status``.

**``Room.housekeeping_status`` is the one column here with a revenue consequence.** OUT_OF_ORDER
takes a room off sale, so Task 4's per-date allotment counter has to move with it. That works only
if the column has exactly ONE writer, so it is deliberately absent from the update schema and moved
only by ``service/rooms.set_housekeeping_status`` — the housekeeping board goes through the same
function rather than writing the column itself.
"""

import uuid
from datetime import date

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
from app.core.money import MoneyType
from app.modules.hospitality.constants import (
    HousekeepingStatus,
    HousekeepingTaskStatus,
)


class RoomType(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """WHAT the property sells a night of — a double, a suite, an accessible twin.

    The unit of sale (Q3): availability, rates and bookings all key on the type, and the physical
    room is a check-in decision. ``base_capacity`` is how many guests the type sleeps as standard,
    and it is what a booking's party size is validated against in Task 4; extra beds are a rate
    question this phase does not model (manual rates in v1).

    ``code`` is USER-SUPPLIED and unique per tenant, the ``item_code``/``vendor_code`` shape — a
    master carries a code, not a gapless document number. Audited (D-010): a room type is
    slow-changing structure a manager sets up once, and changing what "DBL" means retroactively
    changes what every rate plan and future booking refers to.
    """

    __tablename__ = "hsp_room_types"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_hsp_room_types_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        sa.CheckConstraint("base_capacity > 0", name="ck_hsp_room_types_capacity_positive"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    base_capacity: Mapped[int] = mapped_column(sa.Integer, nullable=False)


class Room(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """One physical room, and the single fact that decides whether it can be sold tonight.

    ``room_number`` is what the property and the guest both call it ("101", "Garden Suite"), unique
    per tenant because a property has one 101. A string rather than an integer: real numbering runs
    ``12A`` and ``PH-2``.

    ``room_type_id`` is a composite tenant FK — this module owns both tables, so the FK costs
    nothing and rules out a room hung off another tenant's inventory (the ``TableReservation``
    ``ticket_id`` precedent, as against the opaque cross-module ``item_id``, D-029).

    ``housekeeping_status`` starts DIRTY on a newly added room rather than CLEAN: nobody has made
    it up, and starting sellable is the assumption that turns into a guest walking into an
    unserviced room. Every move is checked against ``HOUSEKEEPING_FLOW`` in the service — this
    column has no CHECK constraint listing the states because a value-set CHECK would have to be
    rewritten by a migration each time the set grows, and the whole set is enumerated in one enum
    the service validates against (the ``OrderTicket.status`` precedent).
    """

    __tablename__ = "hsp_rooms"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "room_number", name="uq_hsp_rooms_tenant_id_room_number"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hsp_room_types", "room_type_id"),
        # PERFORMANCE §1: the two reads this table exists to serve are "every room of this type"
        # (Task 4 counts them to seed ``rooms_sellable``) and "the housekeeping board", which is
        # this table filtered by status. Each filter column gets the tenant-leading index.
        sa.Index("ix_hsp_rooms_tenant_id_room_type_id", "tenant_id", "room_type_id"),
        sa.Index(
            "ix_hsp_rooms_tenant_id_housekeeping_status", "tenant_id", "housekeeping_status"
        ),
    )

    room_number: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    room_type_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    housekeeping_status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=HousekeepingStatus.DIRTY.value,
        server_default="DIRTY",
    )


class RatePlan(UuidPKMixin, TenantMixin, AuditMixin, TimestampMixin, Base):
    """What one night of a room type costs, over a validity window.

    MANUAL in v1, deliberately (plan Task 3): one nightly amount per plan, and a window it applies
    over — no per-date rate calendar, no yield rules, no length-of-stay pricing. A property that
    wants a seasonal rate makes a second plan with a second window. The window is the whole of the
    date handling, which is why the only rule the database enforces is that it is not backwards.

    ``nightly_amount`` is a ``MoneyType`` (D-015, exact on both engines) paired with an explicit
    ``currency_code``, the ``money pairs amount+currency_code`` convention (STRUCTURE §7). The
    currency is a plain 3-char code with no FK: ``fin_currencies`` belongs to finance and
    hospitality references it the way every other module does (D-029), so the code is validated
    where it is spent, not where it is typed.

    Prices the room TYPE, never a room: a guest buys a double, and which double they get is a
    check-in decision. A per-room price would make the desk's room assignment a pricing decision.
    """

    __tablename__ = "hsp_rate_plans"
    __table_args__ = (
        sa.UniqueConstraint("tenant_id", "code", name="uq_hsp_rate_plans_tenant_id_code"),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hsp_room_types", "room_type_id"),
        sa.CheckConstraint("nightly_amount >= 0", name="ck_hsp_rate_plans_amount_non_negative"),
        # The backstop under the service's ``hospitality.rate_plan_window_invalid`` refusal. A
        # plain CHECK, portable on both engines (D-003); NULL valid_to means open-ended and a NULL
        # comparison is UNKNOWN, which a CHECK treats as satisfied — the intended reading.
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_hsp_rate_plans_window_ordered",
        ),
        sa.Index("ix_hsp_rate_plans_tenant_id_room_type_id", "tenant_id", "room_type_id"),
    )

    code: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    room_type_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    nightly_amount: Mapped[object] = mapped_column(MoneyType(), nullable=False)
    currency_code: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    valid_from: Mapped[date] = mapped_column(sa.Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(sa.Date, nullable=True)


class HousekeepingTask(
    UuidPKMixin, TenantMixin, AuditMixin, DocumentMixin, TimestampMixin, Base
):
    """One unit of housekeeping work — a D-012 DOCUMENT, numbered ``HKT-2026-000001`` at creation.

    A document rather than a flag on the room, because it is a thing a property refers to: the
    board quotes it, an attendant is assigned to it, a supervisor closes it, and a guest complaint
    about a room is answered by pointing at the task that says who serviced it and when. Numbered
    at creation on the order-ticket branch — it is referenceable the moment it is raised, so there
    is no draft phase to defer the claim to.

    ``trigger`` is stored, never inferred. A departure clean, a scheduled service and a guest's
    mid-stay request produce identical work and are counted separately by every property that
    measures housekeeping, and the reservation that caused a CHECKOUT task is gone from the board
    by the time anybody asks.

    ``assigned_user_id`` is a core ``adm_users`` id kept as a PLAIN id with no FK — the
    ``QualityInspection.decision_by`` and journal ``posted_by`` precedent. Nullable: the board is
    raised by the system at check-out and assigned by a human afterwards.

    ``status`` is the WORK ORDER's progress and is not the same fact as ``Room.housekeeping_status``
    next door: a task can be cancelled while the room stays exactly as dirty as it was, and a room
    can be made clean with no task at all. The service keeps them in step by calling
    ``rooms.set_housekeeping_status`` — one writer for the column with the revenue consequence.
    """

    __tablename__ = "hsp_housekeeping_tasks"
    __table_args__ = (
        sa.UniqueConstraint(
            "tenant_id", "task_number", name="uq_hsp_housekeeping_tasks_tenant_id_task_number"
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hsp_rooms", "room_id"),
        document_fk(),
        # PERFORMANCE §1: the board is read as "what is outstanding" and "what is happening in
        # 101", so both filter columns carry the tenant-leading index. Every FK column is indexed,
        # no exceptions.
        sa.Index("ix_hsp_housekeeping_tasks_tenant_id_room_id", "tenant_id", "room_id"),
        sa.Index("ix_hsp_housekeeping_tasks_tenant_id_status", "tenant_id", "status"),
    )

    task_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    trigger: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=HousekeepingTaskStatus.OPEN.value,
        server_default="OPEN",
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


__all__ = ["HousekeepingTask", "RatePlan", "Room", "RoomType"]
