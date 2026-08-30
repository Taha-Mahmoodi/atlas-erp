"""Restaurant TABLE-reservation models (PLAN 21): the property's pacing settings, the per-slot
counter, and the reservation document itself.

Named for the tables it holds (``hsp_reservation_settings``, ``hsp_service_slots``,
``hsp_table_reservations``) rather than the bare word "reservations", because Phase 20 adds a
second, unrelated reservation — a guest booking a ROOM — whose models live in ``rooms.py``. A
dining-room booking holds a 15-minute pacing slot; a room booking holds a room-night allotment.
They share a word and nothing else.

The pacing counter is the unit of availability, not a table: OpenTable and Resy both cap covers per
slot and leave the physical table a revisable soft assignment made by a human at seating, so
``table_code`` stays the free text ``ordering.OrderTicket`` already carries and this module owns no
table master.
"""

import uuid
from datetime import date, datetime, time

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
    DEFAULT_BOOKING_HORIZON_DAYS,
    DEFAULT_COVERS_MAX,
    DEFAULT_MAX_PARTY,
    DEFAULT_MIN_PARTY,
    DEFAULT_PARTIES_MAX,
    DEFAULT_SERVICE_CLOSE,
    DEFAULT_SERVICE_OPEN,
    ReservationStatus,
)


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


__all__ = ["ReservationSettings", "ServiceSlot", "TableReservation"]
