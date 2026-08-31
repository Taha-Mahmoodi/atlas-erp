"""Hospitality models package (STRUCTURE §3/§8.4: the single ``models.py`` reached 451 lines after
Phase 21, past the 400-line cap #176 tracks, and Phase 20's rooms/folio tables cannot go into a file
that is already over it — the finance/inventory/sales ``models/`` precedent).

Re-exports every model so ``from app.modules.hospitality.models import OrderTicket`` (and
``MenuAvailability``, ``TableReservation``, ...) keeps working from ONE surface, and so every
importer — ``alembic/env.py``, the ``tests/core/test_tenancy.py`` mapper-enumeration suite, the
package ``__init__``'s D-007 registration hook — registers all tables on ``Base.metadata``.

- ``ordering``: the stored 86 board and the order ticket + its lines — the CHECK (19.1–19.2).
- ``menu``: how a property organises what it sells — the section tree, a dish's placement in it,
  and flat tags (#212, D-081).
- ``table_reservations``: restaurant pacing settings, the per-slot counter and the table-booking
  document (Phase 21). Named for its tables, not "reservations", because Phase 20's ROOM booking is
  a different concept in ``rooms.py``.

- ``rooms``: the HOTEL side (Phase 20.1) — the room type a night is sold of, the physical room, the
  manual rate plan, and the housekeeping task document. Task 4's ``RoomTypeInventory`` allotment
  counter and its ROOM reservation document join it (or a ``room_inventory.py`` sibling if the
  §8.4 cap is close by then), and Task 5's ``Folio``/``FolioLine`` plus Task 6's business-date row
  get a ``folio.py``.

Each new model is imported and listed below in the same shape; nothing outside this package
declares a hospitality table. That is not cosmetic: ``alembic/env.py`` imports only this package,
so a model missing here is invisible to autogenerate and its table gets proposed for DROP.
"""

from app.modules.hospitality.models.menu import (
    MAX_SECTION_DEPTH,
    MenuItemTag,
    MenuPlacement,
    MenuSection,
)
from app.modules.hospitality.models.ordering import (
    MenuAvailability,
    OrderTicket,
    OrderTicketLine,
)
from app.modules.hospitality.models.rooms import (
    HousekeepingTask,
    RatePlan,
    Room,
    RoomType,
)
from app.modules.hospitality.models.table_reservations import (
    ReservationSettings,
    ServiceSlot,
    TableReservation,
)

__all__ = [
    "MAX_SECTION_DEPTH",
    "HousekeepingTask",
    "MenuAvailability",
    "MenuItemTag",
    "MenuPlacement",
    "MenuSection",
    "OrderTicket",
    "OrderTicketLine",
    "RatePlan",
    "ReservationSettings",
    "Room",
    "RoomType",
    "ServiceSlot",
    "TableReservation",
]
