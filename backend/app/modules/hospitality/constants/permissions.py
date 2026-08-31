"""Hospitality permission keys (D-009), registered into the core RBAC catalog at import.

Split out of the single ``constants.py`` at the STRUCTURE §8.4 400-line cap (the
``sales/constants/permissions.py`` precedent). One key per guarded endpoint action; the package
``__init__`` re-exports every name, and importing it is what registers the catalog entries.
"""

from app.core.rbac import register_permissions

# --- Permissions (D-009): one key per guarded endpoint action -----------------
# The menu/ticket split follows the read-vs-manage shape every other module uses, with ONE extra
# key. ``ticket.settle`` is DISTINCT from ``ticket.manage`` because settlement is the money moment —
# it tenders the check and (Phase 20.6) charges a room folio — whereas ``.manage`` opens tickets,
# adds lines and fires them to the kitchen. That is the quality.inspection.decide precedent: the
# action with a financial effect gets its own key so a server can run the floor without being able
# to close out a check.
#
# ``menu.read`` is the key the property's WEBSITE presents (D-069 scoped API key): the whole point
# of the Phase 18 credential is that a website may read the menu and post an order while holding
# nothing else. It is separate from ``menu.manage`` (86-ing a dish, setting a countdown) so a
# leaked website key can never take the kitchen's dishes off the menu.
#
# ``reservation.book`` is the THIRD reservation key and the only one a website ever holds. It is
# separate from ``reservation.read`` because the two answer different questions: a website asks "is
# 19:15 bookable for four" and books it, while ``.read`` is the staff BOOK — every guest's name and
# contact detail for the night. A leaked website key must not be a guest list (D-069's narrowing
# rule: a key is mintable at exactly the width it needs, and no wider).
HOSPITALITY_MENU_READ = "hospitality.menu.read"
HOSPITALITY_MENU_MANAGE = "hospitality.menu.manage"
HOSPITALITY_TICKET_READ = "hospitality.ticket.read"
HOSPITALITY_TICKET_MANAGE = "hospitality.ticket.manage"
HOSPITALITY_TICKET_SETTLE = "hospitality.ticket.settle"
HOSPITALITY_RESERVATION_READ = "hospitality.reservation.read"
HOSPITALITY_RESERVATION_MANAGE = "hospitality.reservation.manage"
HOSPITALITY_RESERVATION_BOOK = "hospitality.reservation.book"

register_permissions(
    HOSPITALITY_MENU_READ,
    HOSPITALITY_MENU_MANAGE,
    HOSPITALITY_TICKET_READ,
    HOSPITALITY_TICKET_MANAGE,
    HOSPITALITY_TICKET_SETTLE,
    HOSPITALITY_RESERVATION_READ,
    HOSPITALITY_RESERVATION_MANAGE,
    HOSPITALITY_RESERVATION_BOOK,
    descriptions={
        HOSPITALITY_MENU_READ: "Read the menu and its availability",
        HOSPITALITY_MENU_MANAGE: "86 a menu item, set a countdown, clear an 86",
        HOSPITALITY_TICKET_READ: "Read order tickets and the kitchen queue",
        HOSPITALITY_TICKET_MANAGE: "Open order tickets, add lines, fire to the kitchen",
        HOSPITALITY_TICKET_SETTLE: "Settle (tender) an order ticket",
        HOSPITALITY_RESERVATION_READ: "Read the reservation book and the slot grid",
        HOSPITALITY_RESERVATION_MANAGE: (
            "Take, amend, seat, cancel and no-show reservations; set pacing capacity"
        ),
        HOSPITALITY_RESERVATION_BOOK: "Check reservation availability and book a table",
    },
)


# --- Rooms and housekeeping (Phase 20.1) --------------------------------------
# Two keys for the master data and a THIRD for housekeeping, on the ``ticket.settle`` precedent: the
# action with an operational consequence gets its own key, so a floor supervisor can run the board —
# raise tasks, start them, mark a room clean or out of order — without being able to edit room
# types, rooms, or the rates they sell at. Taking a room OUT_OF_ORDER stops it being sold, which
# Phase 20 Task 4 turns into a decrement of the per-date allotment: a revenue consequence, and a
# different authority from editing the master.
#
# Reading is ONE key: an attendant's device needs the room list and the board together, and there is
# nothing a reader of one should be denied of the other. No website-facing key here — availability
# and booking are Task 4's surface; the room master, the rate sheet and the board are internal, and
# a leaked website credential must never read that a property has six rooms out of order (D-069's
# narrowing rule).
HOSPITALITY_ROOMS_READ = "hospitality.rooms.read"
HOSPITALITY_ROOMS_MANAGE = "hospitality.rooms.manage"
HOSPITALITY_HOUSEKEEPING_MANAGE = "hospitality.housekeeping.manage"

register_permissions(
    HOSPITALITY_ROOMS_READ,
    HOSPITALITY_ROOMS_MANAGE,
    HOSPITALITY_HOUSEKEEPING_MANAGE,
    descriptions={
        HOSPITALITY_ROOMS_READ: "Read room types, rooms, rate plans and the housekeeping board",
        HOSPITALITY_ROOMS_MANAGE: "Create and edit room types, rooms and rate plans",
        HOSPITALITY_HOUSEKEEPING_MANAGE: (
            "Raise, assign and close housekeeping tasks; set a room's housekeeping status"
        ),
    },
)
