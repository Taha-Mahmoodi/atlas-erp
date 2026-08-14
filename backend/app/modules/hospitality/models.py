"""Hospitality models (PLAN 19): the stored menu-availability row.

ONE table today. Task 4's ``OrderTicket``/``OrderTicketLine`` land here too — STRUCTURE §3 splits
a module into a ``models/`` package only past ~600 lines, and three small tables do not reach it.

CROSS-MODULE IDS ARE OPAQUE (D-029/STRUCTURE §5). ``item_id`` is an inventory ``Item`` id carried
as a plain column with NO FK into ``inv_items``; existence is validated through
``inventory/queries.item_exists`` at write time, the manufacturing-BOM precedent. A menu item IS
an ordinary inventory item — Phase 19 adds no second item entity and no recipe entity.
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
    tenant_unique,
)
from app.core.money import QuantityType
from app.modules.hospitality.constants import AvailabilitySource, AvailabilityState


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
