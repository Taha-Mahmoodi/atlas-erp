"""Hospitality document types, number sequences, docflow link types, event and job keys (D-012).

Split out of the single ``constants.py`` at the STRUCTURE §8.4 400-line cap (the
``sales/constants/documents.py`` precedent). Every hospitality document claims its gapless number AT
CREATION — the order-ticket branch, not finance's number-at-post one — because each of them is
referenceable by a human the moment it exists.
"""


# --- Background depletion (Q4) ------------------------------------------------
# The core/jobs.py key the ingredient-depletion handler registers under. Ingredients are issued
# OFF-REQUEST because a synchronous settle-time depletion fails three measured ways: 38 statements
# per ingredient move, MAX_DISPATCHES_PER_UOW = 50 counted in handler INVOCATIONS (so a 56-line
# ticket is an HTTP 500 while the guest waits to pay), and a phantom stock-out rolling the whole uow
# back on stock the industry's own benchmark says is permanently 2-5% wrong. Task 5 registers the
# handler; the key lives here because Task 8's DECISIONS entry and the job-status endpoint both name
# it and a rename must break in one place.
DEPLETE_TICKET_JOB = "hospitality.deplete_ticket"


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


# --- Housekeeping task (Phase 20.1, D-012) ------------------------------------
# A housekeeping task is a document: the board quotes its number, an attendant is assigned to it, a
# supervisor closes it, and a guest complaint about a room is answered by pointing at the task that
# says who serviced it. Numbered AT CREATION on the order-ticket branch — it is referenceable the
# moment it is raised, so there is no draft phase to defer the claim to. The prefix/padding are the
# CODE defaults ``ensure_sequence`` falls back to, in the same shape as the ticket's.
HOUSEKEEPING_TASK_DOC_TYPE = "hospitality.housekeeping_task"
HOUSEKEEPING_TASK_SEQUENCE_NAME = "hospitality.housekeeping_task"
HOUSEKEEPING_TASK_NUMBER_PREFIX = "HKT"
HOUSEKEEPING_TASK_NUMBER_PADDING = 6

# The docflow link type joining whatever RAISED a task to the task, so
# ``GET /api/v1/documents/{id}/chain`` renders reservation -> housekeeping task once Task 4's
# check-out passes the departing reservation's document id through
# ``HousekeepingTaskCreate.predecessor_document_id``.
HOUSEKEEPING_TRIGGERED_BY_LINK = "triggers_housekeeping"
