"""Hospitality constants (STRUCTURE §3): the menu-availability enums, the permission keys
registered into the core RBAC catalog at import (D-009), and the background-job key the depletion
handler registers under.

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap). Ticket
statuses, the document type and the numbering prefix land here alongside their model in Task 4;
declaring them before anything reads them would be the dead config STRUCTURE §8.3 forbids.
"""

from enum import StrEnum

from app.core.rbac import register_permissions


class AvailabilityState(StrEnum):
    """What the guest read path says about a sellable menu item (spec Q2).

    STORED, never derived. ``atp_check`` costs 3 queries per item and its
    ``on_hand - committed + on_order`` formula lets tomorrow's delivery make tonight's dish read
    available; decisively, ``collection_etag`` (``core/conditional.py``) is
    ``COUNT(id), MAX(updated_at)``, so a derived answer never invalidates — selling the last
    portion moves no ``Item.updated_at`` and the website keeps its 304. A row of stored state the
    ETag aggregates over invalidates for free. This is also why the state does NOT live on
    ``Item.is_active``: that flag is filter-only (``item_exists`` never reads it), it hides the
    item from purchasing and costing too, and ``Item`` carries ``AuditMixin`` — an audit row per
    flip for a toggle a kitchen throws dozens of times a night.

    Toast, Square and Lightspeed all converge on these three; the names follow the kitchen's own
    vocabulary rather than inventing a fourth.

    - **AVAILABLE** — sellable. The DEFAULT: an item with no row at all reads AVAILABLE, because
      absence of an override is not unavailability.
    - **LIMITED** — sellable with a countdown. ``remaining_qty`` is the portions left; every order
      decrements it and the row flips to EIGHTY_SIXED at zero (``source`` becomes AUTO). This is
      what Toast's and Square's "auto-86" actually is — a per-item counter, NOT a recipe
      explosion.
    - **EIGHTY_SIXED** — off the menu. Set by a human ("out of feta") or reached by a countdown.
      The website must not offer it and ``fire_ticket`` (Task 4) refuses it.
    """

    AVAILABLE = "AVAILABLE"
    LIMITED = "LIMITED"
    EIGHTY_SIXED = "EIGHTY_SIXED"


class AvailabilitySource(StrEnum):
    """WHO last wrote the availability row — the audit substitute for a table that deliberately
    carries no ``AuditMixin`` (see ``AvailabilityState``: 86-ing is shift-scoped churn, not a
    security-relevant change worth a before/after row per flip).

    - **MANUAL** — a human set it through the staff endpoint.
    - **AUTO** — the countdown hit zero and flipped the row itself.
    """

    MANUAL = "MANUAL"
    AUTO = "AUTO"

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
HOSPITALITY_MENU_READ = "hospitality.menu.read"
HOSPITALITY_MENU_MANAGE = "hospitality.menu.manage"
HOSPITALITY_TICKET_READ = "hospitality.ticket.read"
HOSPITALITY_TICKET_MANAGE = "hospitality.ticket.manage"
HOSPITALITY_TICKET_SETTLE = "hospitality.ticket.settle"

register_permissions(
    HOSPITALITY_MENU_READ,
    HOSPITALITY_MENU_MANAGE,
    HOSPITALITY_TICKET_READ,
    HOSPITALITY_TICKET_MANAGE,
    HOSPITALITY_TICKET_SETTLE,
    descriptions={
        HOSPITALITY_MENU_READ: "Read the menu and its availability",
        HOSPITALITY_MENU_MANAGE: "86 a menu item, set a countdown, clear an 86",
        HOSPITALITY_TICKET_READ: "Read order tickets and the kitchen queue",
        HOSPITALITY_TICKET_MANAGE: "Open order tickets, add lines, fire to the kitchen",
        HOSPITALITY_TICKET_SETTLE: "Settle (tender) an order ticket",
    },
)

# --- Background depletion (Q4) ------------------------------------------------
# The core/jobs.py key the ingredient-depletion handler registers under. Ingredients are issued
# OFF-REQUEST because a synchronous settle-time depletion fails three measured ways: 38 statements
# per ingredient move, MAX_DISPATCHES_PER_UOW = 50 counted in handler INVOCATIONS (so a 56-line
# ticket is an HTTP 500 while the guest waits to pay), and a phantom stock-out rolling the whole uow
# back on stock the industry's own benchmark says is permanently 2-5% wrong. Task 5 registers the
# handler; the key lives here because Task 8's DECISIONS entry and the job-status endpoint both name
# it and a rename must break in one place.
DEPLETE_TICKET_JOB = "hospitality.deplete_ticket"
