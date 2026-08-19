"""Hospitality constants (STRUCTURE §3): the menu-availability enums, the permission keys
registered into the core RBAC catalog at import (D-009), and the background-job key the depletion
handler registers under.

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap).
"""

from datetime import time
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


class OrderTicketStatus(StrEnum):
    """Lifecycle of an ORDER TICKET — the check for one table (PLAN 19 Task 4).

    The order of declaration IS the lifecycle: ``TICKET_FLOW`` below reads it positionally and a
    transition is legal only to the NEXT state. Strictly sequential, and the reason is Q4 rather
    than tidiness — SENT_TO_KITCHEN is the single point where a ticket's ingredients are consumed,
    so any shortcut past it would be revenue with no depletion at all.

    - **OPEN** — the server seated the table and is taking the order. The ONLY state in which lines
      may be added: a fired line is already being cooked and already counted for depletion.
    - **SENT_TO_KITCHEN** — fired. This is the commitment moment: an 86'd dish is refused here, a
      countdown burns here, and ``RestaurantOrderFired`` is published here so Task 5 can deplete
      ingredients OFF the request. Not at tender — a dish comped after service has already eaten
      its ingredients, and a depletion hanging off settle would block the guest's payment (Q4).
    - **IN_PREP** / **READY** / **SERVED** — the kitchen's own progress, moved by the KDS (a
      status-filtered query over open ticket lines, not new infrastructure). No stock or money
      effect; they exist so the floor can see where a check is.
    - **SETTLED** — tendered. Terminal. Publishes ``RestaurantOrderSettled``, which is what Phase
      20.6's room-charge bridge will subscribe to. Phase 19 takes no payment itself (Q1's provider
      interface is Phase 20+).
    - **CANCELLED** — terminal, and reachable ONLY from OPEN (D-080). A check opened on the wrong
      table, or for a party that walked before ordering, has cooked nothing and moved no money, so
      closing it costs nothing and leaving it OPEN forever is what the floor actually complained
      about. It is deliberately NOT reachable after firing: the ingredients have already left the
      storeroom by then, and a comp or a walk-out on a fired check is a money correction the Phase
      20 folio owns — inventing a terminal state that silently un-cooks food would be worse than
      not having one.
    """

    OPEN = "OPEN"
    SENT_TO_KITCHEN = "SENT_TO_KITCHEN"
    IN_PREP = "IN_PREP"
    READY = "READY"
    SERVED = "SERVED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


# The SEQUENTIAL lifecycle as an ordered tuple — the whole forward-transition rule is "index + 1",
# so there is no transition table to keep in sync with the enum. Declared next to the enum because
# the ORDER is the contract, not just the membership.
#
# CANCELLED is deliberately NOT in it: it is a branch off OPEN, not a step in the sequence, and
# putting it in the tuple would both make SETTLED -> CANCELLED a legal "next" move and change what
# the index arithmetic means. Its one transition is checked by ``cancel_ticket`` instead.
TICKET_FLOW: tuple[OrderTicketStatus, ...] = tuple(
    status for status in OrderTicketStatus if status is not OrderTicketStatus.CANCELLED
)

# The states a plain kitchen/floor progress update may set. Firing and settling are deliberately
# NOT here: each carries effects (the 86 check + countdown + the fired event; the settled event)
# that a generic status PATCH must never be able to skip past.
TICKET_PROGRESS_STATES: frozenset[OrderTicketStatus] = frozenset(
    {OrderTicketStatus.IN_PREP, OrderTicketStatus.READY, OrderTicketStatus.SERVED}
)


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

# --- Background depletion (Q4) ------------------------------------------------
# The core/jobs.py key the ingredient-depletion handler registers under. Ingredients are issued
# OFF-REQUEST because a synchronous settle-time depletion fails three measured ways: 38 statements
# per ingredient move, MAX_DISPATCHES_PER_UOW = 50 counted in handler INVOCATIONS (so a 56-line
# ticket is an HTTP 500 while the guest waits to pay), and a phantom stock-out rolling the whole uow
# back on stock the industry's own benchmark says is permanently 2-5% wrong. Task 5 registers the
# handler; the key lives here because Task 8's DECISIONS entry and the job-status endpoint both name
# it and a rename must break in one place.
DEPLETE_TICKET_JOB = "hospitality.deplete_ticket"

# How many DISTINCT components one depletion job may issue. Backgrounding alone does NOT lift the
# D-011 ceiling: the job runner executes its handler inside ``run_in_uow`` too (core/jobs.py:303),
# so ``MAX_DISPATCHES_PER_UOW = 50`` applies to the job's transaction exactly as it applies to a
# request's. MEASURED on this branch by running real depletion jobs at increasing widths: one ISSUE
# move costs exactly ONE dispatch (StockValued -> the finance COGS handler) and the
# TicketIngredientsConsumed event itself costs one more, so 49 components COMPLETE and 50 FAIL with
# EventCycleError. 40 keeps a working margin, and an aggregate above it is SPLIT across
# several jobs rather than refused — the plan's stated residual risk ("an extreme ticket could
# still approach 50 dispatches") closed rather than documented. The inline/background threshold
# shape it mirrors is COUNT_POST_SYNC_MAX_VARIANCES (inventory/constants.py); the difference is
# that depletion has no inline branch at all, because Q4's phantom-stock-out argument applies to a
# one-line ticket exactly as it applies to a fifty-line one.
DEPLETE_MAX_COMPONENTS_PER_JOB = 40

# docflow link type (D-012) joining a fired ticket's document to each ingredient ISSUE move the
# depletion job posts: the ticket "depleted" the stock. Declared HERE, in the publishing module,
# following the sales/procurement/manufacturing precedent — inventory's handler imports it to write
# the edge from the side that owns the move.
TICKET_DEPLETED_BY_MOVE_LINK = "depleted_by"

# --- Order-ticket document type, numbering + event keys (Task 4, D-012/D-011) ---------------
# An order ticket IS a posted document in the D-012 sense: it registers in core_documents and
# claims its gapless number AT CREATION (the sales-order / goods-receipt branch, not finance's
# number-at-post branch) because a ticket is referenceable — by the kitchen, by the guest, by Phase
# 20.6's folio — the moment the server opens it.
#
# The prefix/padding here are the CODE defaults ``ensure_sequence`` falls back to. They match
# ``industry-templates/hospitality.yaml``'s ``numbering_formats.hospitality.order_ticket`` on
# purpose: a tenant that applied the template gets the sequence from the template, a tenant that
# never did gets an identical one from here, and the two must not disagree about what a ticket
# number looks like. ``_format_number`` renders {prefix}-{year}-{padded} -> TKT-2026-000001.
ORDER_TICKET_DOC_TYPE = "hospitality.order_ticket"
ORDER_TICKET_SEQUENCE_NAME = "hospitality.order_ticket"
ORDER_TICKET_NUMBER_PREFIX = "TKT"
ORDER_TICKET_NUMBER_PADDING = 6

# D-011 event keys. Declared here rather than inline in events.py so a subscriber in another module
# (Phase 20.6's folio bridge) and the module documentation name the same constant.
ORDER_TICKET_FIRED_EVENT_KEY = "hospitality.order_ticket.fired"
ORDER_TICKET_SETTLED_EVENT_KEY = "hospitality.order_ticket.settled"
# Published by the DEPLETION JOB, not by the sale — inventory's handler turns it into the ISSUE
# moves. Named for the fact it reports (the ingredients left the storeroom), not for the job.
TICKET_INGREDIENTS_CONSUMED_EVENT_KEY = "hospitality.order_ticket.ingredients_consumed"

# --- The at-risk advisory list (Task 6) ---------------------------------------
# How few portions a dish must be down to before the staff coverage scan reports it. A DEFAULT, not
# a rule: what counts as "running low" is property-specific (a 200-cover brasserie and a 12-seat
# counter disagree), so the endpoint takes it as a query parameter and this is only what a caller
# who does not care gets. Five is roughly one table's worth — enough warning to 86 the dish before
# a server promises it.
AT_RISK_DEFAULT_THRESHOLD = 5


# --- Table reservations (Phase 21, spec Q3) -----------------------------------


class ReservationStatus(StrEnum):
    """Lifecycle of a TABLE RESERVATION (Phase 21).

    There is deliberately NO ``TENTATIVE``/``REQUESTED`` state: passing the pacing gate IS the
    confirmation, which is the OpenTable/Resy model and the reason the gate runs inside the create
    transaction. A "held, pending approval" state would need a sweeper to expire holds, and Atlas
    has no scheduler (the same argument that makes the 86 time box lazily evaluated).

    Unlike ``OrderTicketStatus`` this is NOT a straight line, so it cannot be an ordered tuple read
    positionally — a confirmed booking can be seated, no-showed or cancelled, and only the seated
    one can complete. ``RESERVATION_FLOW`` below is the transition table, declared next to the enum
    for the same reason ``TICKET_FLOW`` is: the legal moves are the contract, not the membership.

    - **CONFIRMED** — booked and counted. The only state that HOLDS capacity.
    - **SEATED** — the party is at a table; ``ticket_id`` points at the check opened for them.
    - **COMPLETED** — they ate and left. Terminal, bookkeeping only.
    - **NO_SHOW** — they never came. Terminal, and it releases NOTHING: it is recorded at or after
      the slot, when there is no longer anything to resell.
    - **CANCELLED** — called off. Releases the capacity IF the slot has not started yet.
    """

    CONFIRMED = "CONFIRMED"
    SEATED = "SEATED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    CANCELLED = "CANCELLED"


# The legal moves, one frozenset per state; an empty set is terminal. A branching lifecycle has no
# "index + 1" rule to lean on, so the table is written out — and written ONCE, here, so the service
# and the docs cannot disagree about whether a SEATED party can still be cancelled (it cannot: they
# are eating, and the correction belongs to their check, not to the booking).
RESERVATION_FLOW: dict[ReservationStatus, frozenset[ReservationStatus]] = {
    ReservationStatus.CONFIRMED: frozenset(
        {ReservationStatus.SEATED, ReservationStatus.NO_SHOW, ReservationStatus.CANCELLED}
    ),
    ReservationStatus.SEATED: frozenset({ReservationStatus.COMPLETED}),
    ReservationStatus.COMPLETED: frozenset(),
    ReservationStatus.NO_SHOW: frozenset(),
    ReservationStatus.CANCELLED: frozenset(),
}

# The pacing grid's width in minutes — a CONSTANT, not a setting. OpenTable and Resy both fix it,
# and it is half of the ``(tenant_id, service_date, slot_start)`` unique key's meaning: making it
# configurable would silently re-point what an already-stored slot row COUNTS the moment a manager
# edited it, with no migration able to say what the old rows meant.
SLOT_MINUTES = 15

# What a tenant that has never written a settings row books against (the MenuAvailability idiom:
# absence is the default, not an error, so a property can take its first booking without being
# configured first). A settings row only ever holds overrides of these.
#
# TIMES ARE UTC. Atlas stores no per-tenant timezone — nothing in the platform has one — so a bare
# wall clock here would be a number nobody could resolve to an instant. The property's website knows
# its own timezone and converts; the staff UI does the same. Named in docs/modules/hospitality.md.
DEFAULT_SERVICE_OPEN = time(11, 0)
DEFAULT_SERVICE_CLOSE = time(23, 0)
DEFAULT_COVERS_MAX = 40
DEFAULT_PARTIES_MAX = 12
DEFAULT_MIN_PARTY = 1
DEFAULT_MAX_PARTY = 12
DEFAULT_BOOKING_HORIZON_DAYS = 90

# D-012 document type + numbering for the reservation, mirroring the order ticket exactly: the
# number is claimed AT CREATION because a reservation is referenceable by the guest and by the floor
# the instant it is confirmed, and there is no draft phase to defer it to.
TABLE_RESERVATION_DOC_TYPE = "hospitality.table_reservation"
TABLE_RESERVATION_SEQUENCE_NAME = "hospitality.table_reservation"
TABLE_RESERVATION_NUMBER_PREFIX = "RSV"
TABLE_RESERVATION_NUMBER_PADDING = 6

# The docflow link type joining a seated reservation to the check opened for that party, so
# ``GET /api/v1/documents/{id}/chain`` renders reservation -> ticket -> (Phase 20 folio line).
RESERVATION_SEATED_AS_TICKET_LINK = "seated_as"
