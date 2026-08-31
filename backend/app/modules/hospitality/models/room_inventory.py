"""The booking gate's two tables (PLAN 20.2): what a room type has left to sell on one night, and
the ROOM reservation that consumes it.

A sibling of ``rooms.py`` rather than more of it, exactly as that file's own docstring and the
package ``__init__`` anticipated: ``rooms.py`` is at 217 lines and these two models with the
reasoning they need would take it past the STRUCTURE §8.4 cap. The seam is real rather than
arithmetic — ``rooms.py`` holds the MASTERS a manager sets up once, and this file holds the two
tables that move every time somebody books.

**Rooms sell by TYPE against a per-date counter, not by locking an interval** (spec Q3). The unit of
availability is one ``hsp_room_type_inventory`` row per ``(room_type, stay_date)``, locked
``with_for_update`` in the booking transaction, refused pre-flight, with a portable CHECK pair as
the backstop — ``inventory/service/stock_quants.apply_bin_delta`` in shape (D-020/D-036), and the
same shape the restaurant's ``ServiceSlot`` uses one file over. The alternative Q3 rejects, an
``EXCLUDE USING gist`` over a date range, is PostgreSQL-only and would leave the SQLite suite
(D-003) unable to test the invariant it depends on.

**Naming.** ``RoomReservation`` next to ``TableReservation``, never a bare ``Reservation``: this
module holds a restaurant booking (a 15-minute pacing slot) and a hotel booking (a room-night
allotment), they share a word and nothing else, and a reader must not have to guess which one a name
means. Same rule for the table names, the status enum and every constant.
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
from app.modules.hospitality.constants import (
    DEFAULT_OVERBOOKING_LIMIT,
    RoomReservationStatus,
)


class RoomTypeInventory(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """THE ALLOTMENT COUNTER: how many rooms of one type are sellable on one night, and how many of
    them are sold (spec Q3).

    Three integers, and each is a different fact:

    - ``rooms_sellable`` — the physical supply. Seeded at materialisation from a COUNT of the
      type's rooms that are not in ``HOUSEKEEPING_UNSELLABLE``, and moved thereafter only by
      ``rooms.set_housekeeping_status`` (D-085's single writer). A SNAPSHOT, like
      ``ServiceSlot.covers_max``: adding a room to the property does not reach back into nights
      already being sold, which is the honest reading and keeps the counter a counter.
    - ``rooms_sold`` — what confirmed bookings hold. The only column a booking moves.
    - ``overbooking_limit`` — how far past the supply the property is willing to sell, per night.
      Zero by default (``DEFAULT_OVERBOOKING_LIMIT``): overbooking is a deliberate revenue decision,
      and it is what pays for ``NO_SHOW`` releasing nothing — the buffer is sold in advance against
      the guests who never arrive, so releasing a no-show's night would spend it twice.

    **A missing row means the DEFAULT supply, not zero** — the ``ServiceSlot`` rule, and for the
    same reason: pre-materialising a grid would be one row per room type per night forever, for
    nights nobody books, which is the grid-maintenance trap Q3 names. The row is created lazily by
    the first counter touch, seeded from the live room count. Compare ``StockQuant``, where absence
    genuinely means nothing on hand: supply here is standing structure, not a balance.

    Deliberately NOT ``AuditMixin`` (the ``ServiceSlot``/``MenuAvailability`` argument): this row is
    written on every confirmation and every cancellation, so a before/after diff per write would
    charge the guest's request for a second insert and produce noise nobody reads. The RESERVATION
    is the audited document, and it is what a dispute is settled from.

    The two CHECKs are the DB backstop under the service's pre-flight refusal, the
    ``inv_stock_quants`` shape (D-020/D-036): ``adjust_allotment`` refuses
    ``hospitality.room_type_sold_out`` BEFORE writing, and the CHECK is what fires if that is ever
    bypassed. Plain CHECKs, so they hold on both engines (D-003).
    """

    __tablename__ = "hsp_room_type_inventory"
    __table_args__ = (
        # One counter per (room type, night). Doubles as the index every read of this table uses:
        # the leading (tenant_id, room_type_id) columns serve "this type's next 30 nights" from one
        # scan, so no second index is declared (PERFORMANCE §1).
        sa.UniqueConstraint(
            "tenant_id",
            "room_type_id",
            "stay_date",
            name="uq_hsp_room_type_inventory_tenant_id_room_type_id_stay_date",
        ),
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("hsp_room_types", "room_type_id"),
        sa.CheckConstraint("rooms_sold >= 0", name="ck_hsp_room_type_inventory_sold_non_negative"),
        sa.CheckConstraint(
            "rooms_sold <= rooms_sellable + overbooking_limit",
            name="ck_hsp_room_type_inventory_sold_within_supply",
        ),
        sa.CheckConstraint(
            "rooms_sellable >= 0 AND overbooking_limit >= 0",
            name="ck_hsp_room_type_inventory_supply_non_negative",
        ),
    )

    room_type_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    # The NIGHT, not a range: a stay is N rows, one per night slept, and the departure date is never
    # one of them. That is what makes back-to-back stays (out on the 5th, in on the 5th) sell the
    # same room twice without any interval arithmetic.
    stay_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    rooms_sellable: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    rooms_sold: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    overbooking_limit: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=DEFAULT_OVERBOOKING_LIMIT,
        server_default=str(DEFAULT_OVERBOOKING_LIMIT),
    )


class RoomReservation(UuidPKMixin, TenantMixin, AuditMixin, DocumentMixin, TimestampMixin, Base):
    """A booked stay (PLAN 20.2) — a D-012 document, numbered ``RMR-2026-000001`` at creation.

    Numbered at creation even though it starts TENTATIVE and holds nothing: the number is the
    confirmation reference the website shows the guest and the desk searches on, so it exists before
    the sale does. Audited (D-010) because a reservation is a promise to a named guest that staff
    move, cancel and mark no-show, and "who changed my booking" is the question the audit log
    answers.

    **``room_type_id`` is what is SOLD; ``room_id`` is what is OCCUPIED.** The guest buys a double
    and which double they get is a check-in decision (Q3), which is why the counter keys on the type
    and why ``room_id`` is nullable until CHECKED_IN. Both are composite tenant FKs — this module
    owns both tables, so the FK costs nothing and rules out a booking hung off another tenant's
    inventory (the ``TableReservation.ticket_id`` precedent, as against the opaque cross-module
    ``item_id``, D-029).

    **The stay is [arrival, departure), and the departure night is never sold.** A guest arriving on
    the 3rd and leaving on the 5th sleeps two nights, so the CHECK is strict: a stay of zero nights
    is a booking for nobody occupying a room somebody else could have had.

    ``rate_plan_id`` is required, not optional: a booking nobody can price is a booking the Task 7
    night audit cannot post revenue for, and "we will work the rate out later" is how a folio ends
    up empty. The service checks the plan prices THIS room type — otherwise a suite sells at a
    single's rate through nothing worse than a copy-pasted id.
    """

    __tablename__ = "hsp_room_reservations"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        document_fk(),
        tenant_fk("hsp_room_types", "room_type_id"),
        tenant_fk("hsp_rate_plans", "rate_plan_id"),
        # Nullable until check-in; a NULL composite FK is simply not enforced (MATCH SIMPLE).
        tenant_fk("hsp_rooms", "room_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "reservation_number",
            name="uq_hsp_room_reservations_tenant_id_reservation_number",
        ),
        sa.CheckConstraint(
            "departure_date > arrival_date",
            name="ck_hsp_room_reservations_stay_at_least_one_night",
        ),
        sa.CheckConstraint("party_size > 0", name="ck_hsp_room_reservations_party_size_positive"),
        # PERFORMANCE §1: the book is read as "arrivals from this date, optionally in state X",
        # ordered by arrival — (tenant, arrival_date) serves the filter AND the sort from one index.
        sa.Index(
            "ix_hsp_room_reservations_tenant_id_arrival_date", "tenant_id", "arrival_date"
        ),
        # Every FK column gets an index, no exceptions. The room-type one also serves the
        # availability question "which bookings hold this type"; the room one serves the desk's
        # "who is in 101".
        sa.Index(
            "ix_hsp_room_reservations_tenant_id_room_type_id", "tenant_id", "room_type_id"
        ),
        sa.Index("ix_hsp_room_reservations_tenant_id_room_id", "tenant_id", "room_id"),
        sa.Index(
            "ix_hsp_room_reservations_tenant_id_rate_plan_id", "tenant_id", "rate_plan_id"
        ),
    )

    reservation_number: Mapped[str] = mapped_column(sa.String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        default=RoomReservationStatus.TENTATIVE.value,
        server_default="TENTATIVE",
    )
    room_type_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    rate_plan_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    arrival_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    departure_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    party_size: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    room_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    guest_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # ONE free-text field, the ``TableReservation.guest_contact`` argument: the website has already
    # authenticated its guest (Q1) and owns notification; Atlas stores what the desk needs to call.
    guest_contact: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)


__all__ = ["RoomReservation", "RoomTypeInventory"]
