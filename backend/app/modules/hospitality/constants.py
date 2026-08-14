"""Hospitality constants (STRUCTURE §3): the permission keys registered into the core RBAC catalog
at import (D-009), and the background-job key the depletion handler registers under.

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap). Ticket
statuses, the document type and the numbering prefix land here alongside their model in Task 4;
declaring them before anything reads them would be the dead config STRUCTURE §8.3 forbids.
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
